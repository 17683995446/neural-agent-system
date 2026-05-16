"""
神经网络多Agent系统 — LLM服务最大并发量测试 (真实LLM)

使用硅基流动API, 每次请求和回复均打印
测试维度:
1. LLMClient.complete() 同步并发 — 不同max_concurrent下的真实吞吐
2. LLMClient.acomplete() 异步并发 — 发现无限制频风险
3. CheapLLMClient.complete() 并发 — 无限制频表现
4. 多模型混合并发 — Qwen3-8B + DeepSeek-V3 + GLM-4-9B
"""

import sys
import os
import time
import asyncio
import threading
import concurrent.futures
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SILICONFLOW_API_KEY = "sk-uqelhavcdhfxjzjesdenxpbtqombamjniazzjtbssmdcwdvg"
SILICONFLOW_BASE = "https://api.siliconflow.cn/v1/chat/completions"

MODELS = {
    "Qwen3-8B": "Qwen/Qwen3-8B",
    "DeepSeek-V3": "deepseek-ai/DeepSeek-V3",
    "GLM-4-9B": "THUDM/GLM-4-9B-0414",
}

DEFAULT_MODEL = MODELS["Qwen3-8B"]

from app.core.llm_rate_limiter import LLMRateLimiter
from app.core.llm_client import LLMClient
from app.core.cheap_llm_client import CheapLLMClient


@dataclass
class RequestLog:
    idx: int
    thread_id: int
    model: str
    prompt: str
    reply: str
    start_ms: float
    end_ms: float
    latency_ms: float
    success: bool
    error: Optional[str] = None
    tokens: int = 0


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def print_request(log: RequestLog):
    status = "OK" if log.success else "FAIL"
    print(f"  [{ts()}] #{log.idx:<3} T{log.thread_id:<3} {status} {log.latency_ms:>7.0f}ms | model={log.model}")
    print(f"         REQ: {log.prompt[:80]}")
    if log.success:
        print(f"         REP: {log.reply[:120]}{'...' if len(log.reply) > 120 else ''}")
    else:
        print(f"         ERR: {log.error[:120] if log.error else 'unknown'}")
    if log.tokens > 0:
        print(f"         TOK: {log.tokens}")


def analyze_logs(logs: List[RequestLog], name: str):
    ok = [l for l in logs if l.success]
    fail = [l for l in logs if not l.success]
    latencies = [l.latency_ms for l in ok]
    if not latencies:
        print(f"\n  [{name}] 全部失败! {len(fail)} errors")
        return

    wall_start = min(l.start_ms for l in logs)
    wall_end = max(l.end_ms for l in logs)
    wall_s = (wall_end - wall_start) / 1000

    sorted_lat = sorted(latencies)
    p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
    p99 = sorted_lat[min(int(len(sorted_lat) * 0.99), len(sorted_lat) - 1)]

    total_tokens = sum(l.tokens for l in ok)

    time_events = []
    for l in ok:
        time_events.append((l.start_ms, 1))
        time_events.append((l.end_ms, -1))
    time_events.sort()
    cur = peak = 0
    for _, d in time_events:
        cur += d
        peak = max(peak, cur)

    print(f"\n{'='*70}")
    print(f"  [{name}] 统计摘要")
    print(f"{'='*70}")
    print(f"  请求: {len(logs)} 发出, {len(ok)} 成功, {len(fail)} 失败")
    print(f"  耗时: {wall_s:.2f}s (墙钟)")
    print(f"  QPS:  {len(ok)/wall_s:.2f}")
    print(f"  延迟: avg={sum(latencies)/len(latencies):.0f}ms, p50={p50:.0f}ms, p95={p95:.0f}ms, p99={p99:.0f}ms, max={max(latencies):.0f}ms")
    print(f"  峰值并发: {peak}")
    print(f"  总tokens: {total_tokens}")
    print(f"{'='*70}")


# ============================================================
# Test 1: LLMClient.complete() 同步并发 — 找最大并发吞吐
# ============================================================
def test_sync_concurrency():
    print("\n" + "=" * 70)
    print("  TEST 1: LLMClient.complete() 同步并发 — 真实LLM")
    print("=" * 70)

    concurrency_levels = [1, 2, 3, 5, 8]
    logs_all: List[RequestLog] = []
    counter = threading.Lock()
    idx = [0]

    for n in concurrency_levels:
        LLMRateLimiter.configure(max_qps=n * 2.0, max_concurrent=n)
        client = LLMClient(
            model=DEFAULT_MODEL,
            api_key=SILICONFLOW_API_KEY,
            api_base="https://api.siliconflow.cn",
            max_tokens=50,
            temperature=0.3,
        )

        logs: List[RequestLog] = []
        prompts = [f"用一句话回答: {i+1}加{i+1}等于几?" for i in range(n)]

        print(f"\n  --- 并发数={n}, max_concurrent={n}, max_qps={n*2.0} ---")

        def worker(prompt: str, worker_id: int):
            with counter:
                cur_idx = idx[0]
                idx[0] += 1
            start = time.monotonic()
            try:
                resp = client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    fallback_text="[fallback]",
                )
                end = time.monotonic()
                text = client.get_response_text(resp)
                usage = resp.get("usage", {})
                total_tok = usage.get("total_tokens", 0)
                log = RequestLog(
                    idx=cur_idx, thread_id=worker_id, model=DEFAULT_MODEL,
                    prompt=prompt, reply=text,
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=True, tokens=total_tok,
                )
            except Exception as e:
                end = time.monotonic()
                log = RequestLog(
                    idx=cur_idx, thread_id=worker_id, model=DEFAULT_MODEL,
                    prompt=prompt, reply="",
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=False, error=str(e),
                )
            print_request(log)
            logs.append(log)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(worker, prompts[i], i) for i in range(n)]
            concurrent.futures.wait(futures)

        analyze_logs(logs, f"同步并发={n}")
        logs_all.extend(logs)

    return logs_all


# ============================================================
# Test 2: LLMClient.acomplete() 异步并发 — 无限制频风险
# ============================================================
async def test_async_concurrency():
    print("\n" + "=" * 70)
    print("  TEST 2: LLMClient.acomplete() 异步并发 — 真实LLM")
    print("=" * 70)

    concurrency_levels = [1, 3, 5, 10]

    for n in concurrency_levels:
        LLMRateLimiter.configure(max_qps=3.0, max_concurrent=3)
        limiter_before = LLMRateLimiter.get_instance().get_stats()

        client = LLMClient(
            model=DEFAULT_MODEL,
            api_key=SILICONFLOW_API_KEY,
            api_base="https://api.siliconflow.cn",
            max_tokens=50,
            temperature=0.3,
        )

        logs: List[RequestLog] = []
        idx = 0
        print(f"\n  --- 异步并发={n}, 限频器max_concurrent=3(应被绕过) ---")

        async def aworker(prompt: str, wid: int):
            nonlocal idx
            cur_idx = idx
            idx += 1
            start = time.monotonic()
            try:
                resp = await client.acomplete(
                    messages=[{"role": "user", "content": prompt}],
                    fallback_text="[fallback]",
                )
                end = time.monotonic()
                text = client.get_response_text(resp)
                usage = resp.get("usage", {})
                total_tok = usage.get("total_tokens", 0)
                log = RequestLog(
                    idx=cur_idx, thread_id=wid, model=DEFAULT_MODEL,
                    prompt=prompt, reply=text,
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=True, tokens=total_tok,
                )
            except Exception as e:
                end = time.monotonic()
                log = RequestLog(
                    idx=cur_idx, thread_id=wid, model=DEFAULT_MODEL,
                    prompt=prompt, reply="",
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=False, error=str(e),
                )
            print_request(log)
            logs.append(log)

        prompts = [f"异步测试: {i+1}的平方是多少?" for i in range(n)]
        tasks = [aworker(prompts[i], i) for i in range(n)]
        await asyncio.gather(*tasks)

        limiter_after = LLMRateLimiter.get_instance().get_stats()
        delta = limiter_after["total_requests"] - limiter_before["total_requests"]
        print(f"\n  限频器total_requests增量: {delta} (如果=0, 确认绕过限频器)")
        print(f"  实际并发发出: {n} (配置max_concurrent=3)")

        analyze_logs(logs, f"异步并发={n}")


# ============================================================
# Test 3: CheapLLMClient 并发 — 无限制频
# ============================================================
def test_cheap_llm_concurrency():
    print("\n" + "=" * 70)
    print("  TEST 3: CheapLLMClient.complete() 并发 — 真实LLM")
    print("=" * 70)

    concurrency_levels = [1, 3, 5, 10]

    for n in concurrency_levels:
        cheap = CheapLLMClient(
            model=DEFAULT_MODEL,
            api_key=SILICONFLOW_API_KEY,
            api_base="https://api.siliconflow.cn",
            max_tokens=50,
            temperature=0.3,
        )

        logs: List[RequestLog] = []
        idx = [0]
        lock = threading.Lock()
        print(f"\n  --- CheapLLM并发={n} (无限频) ---")

        def worker(prompt: str, wid: int):
            with lock:
                cur_idx = idx[0]
                idx[0] += 1
            start = time.monotonic()
            resp = cheap.complete(messages=[{"role": "user", "content": prompt}])
            end = time.monotonic()
            if resp is not None:
                text = cheap.get_response_text(resp)
                usage = resp.get("usage", {})
                total_tok = usage.get("total_tokens", 0)
                log = RequestLog(
                    idx=cur_idx, thread_id=wid, model=DEFAULT_MODEL,
                    prompt=prompt, reply=text,
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=True, tokens=total_tok,
                )
            else:
                log = RequestLog(
                    idx=cur_idx, thread_id=wid, model=DEFAULT_MODEL,
                    prompt=prompt, reply="",
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=False, error="CheapLLM returned None",
                )
            print_request(log)
            logs.append(log)

        prompts = [f"CheapLLM测试: {i+1}乘以2等于?" for i in range(n)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(worker, prompts[i], i) for i in range(n)]
            concurrent.futures.wait(futures)

        stats = cheap.get_stats()
        print(f"\n  CheapLLM stats: calls={stats['total_calls']}, errors={stats['total_errors']}, error_rate={stats['error_rate']:.2%}")
        analyze_logs(logs, f"CheapLLM并发={n}")


# ============================================================
# Test 4: 多模型混合并发
# ============================================================
def test_multi_model_concurrency():
    print("\n" + "=" * 70)
    print("  TEST 4: 多模型混合并发 — 真实LLM")
    print("=" * 70)

    n = 6
    LLMRateLimiter.configure(max_qps=10.0, max_concurrent=6)

    model_names = list(MODELS.keys())
    assignments = []
    for i in range(n):
        m_name = model_names[i % len(model_names)]
        assignments.append((MODELS[m_name], m_name))

    print(f"\n  --- {n}请求, 3模型轮询, max_concurrent=6 ---")
    for i, (m, name) in enumerate(assignments):
        print(f"  请求#{i}: model={name} ({m})")

    logs: List[RequestLog] = []
    idx = [0]
    lock = threading.Lock()

    def worker(model_id: str, model_name: str, prompt: str, wid: int):
        with lock:
            cur_idx = idx[0]
            idx[0] += 1
        client = LLMClient(
            model=model_id,
            api_key=SILICONFLOW_API_KEY,
            api_base="https://api.siliconflow.cn",
            max_tokens=50,
            temperature=0.3,
        )
        start = time.monotonic()
        try:
            resp = client.complete(
                messages=[{"role": "user", "content": prompt}],
                fallback_text="[fallback]",
            )
            end = time.monotonic()
            text = client.get_response_text(resp)
            usage = resp.get("usage", {})
            total_tok = usage.get("total_tokens", 0)
            log = RequestLog(
                idx=cur_idx, thread_id=wid, model=model_name,
                prompt=prompt, reply=text,
                start_ms=start * 1000, end_ms=end * 1000,
                latency_ms=(end - start) * 1000, success=True, tokens=total_tok,
            )
        except Exception as e:
            end = time.monotonic()
            log = RequestLog(
                idx=cur_idx, thread_id=wid, model=model_name,
                prompt=prompt, reply="",
                start_ms=start * 1000, end_ms=end * 1000,
                latency_ms=(end - start) * 1000, success=False, error=str(e),
            )
        print_request(log)
        logs.append(log)

    prompts = [f"用一句话回答: 第{i+1}个质数是什么?" for i in range(n)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(worker, assignments[i][0], assignments[i][1], prompts[i], i) for i in range(n)]
        concurrent.futures.wait(futures)

    analyze_logs(logs, "多模型混合并发")


# ============================================================
# Test 5: 压力测试 — 逐步增大并发直到失败
# ============================================================
def test_stress_find_limit():
    print("\n" + "=" * 70)
    print("  TEST 5: 压力测试 — 找到真实最大并发极限")
    print("=" * 70)

    concurrency_levels = [1, 2, 3, 5, 8, 10, 15, 20]
    results_summary = []

    for n in concurrency_levels:
        LLMRateLimiter.configure(max_qps=n * 3.0, max_concurrent=n)
        client = LLMClient(
            model=DEFAULT_MODEL,
            api_key=SILICONFLOW_API_KEY,
            api_base="https://api.siliconflow.cn",
            max_tokens=30,
            temperature=0.1,
        )

        logs: List[RequestLog] = []
        idx = [0]
        lock = threading.Lock()
        print(f"\n  --- 压力并发={n}, max_concurrent={n}, max_qps={n*3.0} ---")

        def worker(wid: int):
            with lock:
                cur_idx = idx[0]
                idx[0] += 1
            prompt = f"极简回答: {wid+1}+1=?"
            start = time.monotonic()
            try:
                resp = client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    fallback_text="[fallback]",
                )
                end = time.monotonic()
                text = client.get_response_text(resp)
                usage = resp.get("usage", {})
                total_tok = usage.get("total_tokens", 0)
                log = RequestLog(
                    idx=cur_idx, thread_id=wid, model=DEFAULT_MODEL,
                    prompt=prompt, reply=text,
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=True, tokens=total_tok,
                )
            except Exception as e:
                end = time.monotonic()
                log = RequestLog(
                    idx=cur_idx, thread_id=wid, model=DEFAULT_MODEL,
                    prompt=prompt, reply="",
                    start_ms=start * 1000, end_ms=end * 1000,
                    latency_ms=(end - start) * 1000, success=False, error=str(e),
                )
            print_request(log)
            logs.append(log)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(worker, i) for i in range(n)]
            concurrent.futures.wait(futures)

        ok = [l for l in logs if l.success]
        fail = [l for l in logs if not l.success]
        latencies = [l.latency_ms for l in ok]
        wall_start = min(l.start_ms for l in logs) if logs else 0
        wall_end = max(l.end_ms for l in logs) if logs else 0
        wall_s = (wall_end - wall_start) / 1000

        summary = {
            "n": n,
            "ok": len(ok),
            "fail": len(fail),
            "qps": len(ok) / wall_s if wall_s > 0 else 0,
            "avg_ms": sum(latencies) / len(latencies) if latencies else 0,
            "p95_ms": sorted(latencies)[int(len(sorted(latencies)) * 0.95)] if latencies else 0,
            "max_ms": max(latencies) if latencies else 0,
        }
        results_summary.append(summary)
        analyze_logs(logs, f"压力并发={n}")

    print(f"\n{'='*70}")
    print(f"  压力测试汇总")
    print(f"{'='*70}")
    print(f"  {'并发':>6} | {'成功':>4} | {'失败':>4} | {'QPS':>6} | {'平均ms':>8} | {'P95ms':>6} | {'最大ms':>8}")
    print(f"  {'-'*6} | {'-'*4} | {'-'*4} | {'-'*6} | {'-'*8} | {'-'*6} | {'-'*8}")
    for s in results_summary:
        print(f"  {s['n']:>6} | {s['ok']:>4} | {s['fail']:>4} | {s['qps']:>6.2f} | {s['avg_ms']:>8.0f} | {s['p95_ms']:>6.0f} | {s['max_ms']:>8.0f}")


# ============================================================
# Main
# ============================================================
def main():
    print("\n" + "=" * 70)
    print("  神经网络多Agent系统 — LLM服务最大并发量测试")
    print("  使用真实LLM (硅基流动), 每次请求/回复均打印")
    print("=" * 70)
    print(f"  API: {SILICONFLOW_BASE}")
    print(f"  Models: {', '.join(f'{k}={v}' for k, v in MODELS.items())}")
    print(f"  Default: {DEFAULT_MODEL}")

    test_sync_concurrency()
    asyncio.run(test_async_concurrency())
    test_cheap_llm_concurrency()
    test_multi_model_concurrency()
    test_stress_find_limit()

    print("\n" + "=" * 70)
    print("  全部测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
