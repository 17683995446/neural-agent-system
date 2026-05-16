"""
1000 Agents × 100 Iterations 复杂任务全链路压测 (v2)
使用CheapLLMClient + 并发控制, 适配GLM-4-Flash免费模型限流
"""
import asyncio
import time
import json
import os
import statistics
from collections import defaultdict, Counter
from datetime import datetime
from typing import Any, Dict, List

from app.core.cheap_llm_client import CheapLLMClient
from app.core.agent_pool import AgentPool
from app.core.llm_utils import extract_json_from_llm_response, extract_code_from_llm_response

API_KEY = os.getenv("ANTHROPIC_AUTH_TOKEN", "bfccdb7fe8d94be0abb753e48c16c7fe.fMteFrYHmmjJHGUC")
API_BASE = os.getenv("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
MODEL = "glm-4-flash"

NUM_AGENTS = 1000
NUM_ITERATIONS = 100
CONCURRENT_PER_ROUND = 10


def get_text(resp):
    if not resp or "choices" not in resp:
        return ""
    msg = resp["choices"][0].get("message", {})
    return msg.get("content", "") or msg.get("reasoning", "") or ""


def make_cheap():
    return CheapLLMClient(api_key=API_KEY, api_base=API_BASE, model=MODEL)


async def async_cheap_call(prompt, max_tokens=32):
    c = make_cheap()
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, lambda: c.complete([{"role": "user", "content": prompt}], max_tokens=max_tokens))
    return resp


async def run_stress_test():
    print("=" * 80)
    print("  1000 Agents × 100 Iterations 全链路压测验证 (v2)")
    print(f"  Model: {MODEL} | Concurrency: {CONCURRENT_PER_ROUND}/round")
    print(f"  StartTime: {datetime.now().isoformat()}")
    print("=" * 80)

    total_start = time.time()
    all_errors: List[Dict] = []
    iteration_results: List[Dict] = []

    # ============================================================
    # Phase 1: 100轮迭代 — 每轮10 agents并发, 共1000 LLM calls
    # ============================================================
    print("\n" + "-" * 70)
    print("  Phase 1: 100轮迭代 (每轮10 agents并发 = 1000 calls)")
    print("-" * 70)

    phase1_start = time.time()
    phase1_ok = 0
    phase1_total = 0

    for iteration in range(1, NUM_ITERATIONS + 1):
        iter_start = time.time()
        prompts = [
            f"Iter {iteration} Agent {j}: Calculate {j}*{j}+{iteration}. Return only the number."
            for j in range(CONCURRENT_PER_ROUND)
        ]
        tasks = [async_cheap_call(p) for p in prompts]
        resps = await asyncio.gather(*tasks)

        iter_ok = 0
        for j, r in enumerate(resps):
            if r and get_text(r):
                iter_ok += 1
            elif r is None:
                all_errors.append({"phase": 1, "iteration": iteration, "agent": j, "error": "CheapLLM returned None"})
            else:
                all_errors.append({"phase": 1, "iteration": iteration, "agent": j, "error": "Empty response"})

        iter_time = time.time() - iter_start
        phase1_ok += iter_ok
        phase1_total += CONCURRENT_PER_ROUND

        iteration_results.append({
            "iteration": iteration,
            "ok": iter_ok,
            "total": CONCURRENT_PER_ROUND,
            "rate": iter_ok / CONCURRENT_PER_ROUND,
            "time": round(iter_time, 3),
        })

        if iteration % 10 == 0 or iteration <= 3:
            print(f"  Iter {iteration:3d}: {iter_ok}/{CONCURRENT_PER_ROUND} success ({100*iter_ok/CONCURRENT_PER_ROUND:.0f}%) | {iter_time:.2f}s")

    phase1_time = time.time() - phase1_start
    print(f"\n  Phase 1 Summary: {phase1_ok}/{phase1_total} success ({phase1_ok/phase1_total*100:.1f}%) | {phase1_time:.1f}s | {phase1_total/phase1_time:.1f} calls/s")

    # ============================================================
    # Phase 2: 1000 agents AgentPool — 10批×100 agents
    # ============================================================
    print("\n" + "-" * 70)
    print("  Phase 2: AgentPool 1000 agents (10批×100)")
    print("-" * 70)

    phase2_start = time.time()
    phase2_ok = 0
    phase2_total = 0
    batch_details = []

    def agent_fn(item):
        c = make_cheap()
        r = c.complete([{"role": "user", "content": f"Agent {item}: Is {item} a prime number? Answer yes or no."}], max_tokens=32)
        return r

    for batch_idx in range(10):
        bs = time.time()
        pool = AgentPool(max_workers=100)
        items = list(range(batch_idx * 100 + 1, (batch_idx + 1) * 100 + 1))
        results = pool.dispatch_simple(agent_fn, items, timeout=120)
        bok = sum(1 for r in results if r.result is not None)
        bt = time.time() - bs
        phase2_ok += bok
        phase2_total += 100
        batch_details.append({"batch": batch_idx + 1, "ok": bok, "total": 100, "time": round(bt, 2)})
        print(f"  Batch {batch_idx+1:2d}/10: {bok}/100 success | {bt:.1f}s")

    phase2_time = time.time() - phase2_start
    print(f"\n  Phase 2 Summary: {phase2_ok}/{phase2_total} success ({phase2_ok/phase2_total*100:.1f}%) | {phase2_time:.1f}s | {phase2_total/phase2_time:.1f} agents/s")

    # ============================================================
    # Phase 3: 100轮×10 agents Pipeline复杂任务 (生成→审查→测试)
    # ============================================================
    print("\n" + "-" * 70)
    print("  Phase 3: Pipeline复杂任务 (100轮×10 agents × 3 stages = 3000 calls)")
    print("-" * 70)

    phase3_start = time.time()
    phase3_full_ok = 0
    stage_ok = {"generate": 0, "review": 0, "test": 0}
    pipeline_details = []

    for i in range(1, 101):
        iter_start = time.time()

        gen_resps = await asyncio.gather(*[
            async_cheap_call(f"Write a Python function `f_{j}(x)` returning x*{j}+{i}. Just the function.", max_tokens=128)
            for j in range(10)
        ])
        gen_ok = sum(1 for r in gen_resps if r and get_text(r))

        codes = [extract_code_from_llm_response(get_text(r)) or get_text(r) for r in gen_resps]
        review_resps = await asyncio.gather(*[
            async_cheap_call(f"Review this code for bugs:\n```\n{(c or '')[:150]}\n```\nIs it correct? Answer yes/no.", max_tokens=32)
            for c in codes
        ])
        review_ok = sum(1 for r in review_resps if r and get_text(r))

        test_resps = await asyncio.gather(*[
            async_cheap_call(f"Write one assert test for:\n```\n{(c or '')[:150]}\n```", max_tokens=64)
            for c in codes
        ])
        test_ok = sum(1 for r in test_resps if r and get_text(r))

        stage_ok["generate"] += gen_ok
        stage_ok["review"] += review_ok
        stage_ok["test"] += test_ok
        full_ok = min(gen_ok, review_ok, test_ok)
        phase3_full_ok += full_ok

        iter_time = time.time() - iter_start
        pipeline_details.append({"iter": i, "gen": gen_ok, "rev": review_ok, "test": test_ok, "time": round(iter_time, 2)})

        if i % 20 == 0 or i <= 3:
            print(f"  Pipeline iter {i:3d}: gen={gen_ok}/10 rev={review_ok}/10 test={test_ok}/10 | {iter_time:.1f}s")

    phase3_time = time.time() - phase3_start
    print(f"\n  Phase 3 Summary:")
    print(f"    全链路成功: {phase3_full_ok}/1000 agent-stages")
    print(f"    各阶段: 生成={stage_ok['generate']}/1000 审查={stage_ok['review']}/1000 测试={stage_ok['test']}/1000")
    print(f"    总耗时: {phase3_time:.1f}s | 吞吐: {3000/phase3_time:.1f} calls/s")

    # ============================================================
    # Phase 4: 1000 agents一次性全量并发 (Semaphore限流)
    # ============================================================
    print("\n" + "-" * 70)
    print("  Phase 4: 1000 agents一次性并发 (Semaphore=20)")
    print("-" * 70)

    phase4_start = time.time()
    sem = asyncio.Semaphore(20)
    latencies_4 = []
    phase4_ok = 0

    async def bounded_agent(idx):
        async with sem:
            t0 = time.time()
            resp = await async_cheap_call(f"Agent {idx}: What is the {idx}th Fibonacci number mod 100? Just the number.")
            lat = time.time() - t0
            ok = bool(resp and get_text(resp))
            if not ok and resp is None:
                all_errors.append({"phase": 4, "agent": idx, "error": "CheapLLM None"})
            return ok, lat

    results_4 = await asyncio.gather(*[bounded_agent(i) for i in range(1, NUM_AGENTS + 1)])
    for ok, lat in results_4:
        if ok:
            phase4_ok += 1
        latencies_4.append(lat)

    phase4_time = time.time() - phase4_start
    lat_sorted = sorted(latencies_4)
    p50 = lat_sorted[int(len(lat_sorted) * 0.5)]
    p90 = lat_sorted[int(len(lat_sorted) * 0.9)]
    p99 = lat_sorted[int(len(lat_sorted) * 0.99)]
    pmax = lat_sorted[-1]

    print(f"  1000 agents并发: {phase4_ok}/{NUM_AGENTS} success ({phase4_ok/NUM_AGENTS*100:.1f}%)")
    print(f"  耗时: {phase4_time:.1f}s | 吞吐: {NUM_AGENTS/phase4_time:.1f} agents/s")
    print(f"  延迟: P50={p50:.3f}s P90={p90:.3f}s P99={p99:.3f}s Max={pmax:.3f}s")

    # ============================================================
    # 综合报告
    # ============================================================
    total_time = time.time() - total_start
    total_calls = phase1_total + phase2_total + 3000 + NUM_AGENTS
    total_ok = phase1_ok + phase2_ok + sum(stage_ok.values()) + phase4_ok

    iter_rates = [r["rate"] for r in iteration_results]
    iter_times = [r["time"] for r in iteration_results]

    print("\n" + "=" * 80)
    print("  综 合 报 告")
    print("=" * 80)
    print(f"  模型: {MODEL} | API: {API_BASE}")
    print(f"  验证时间: {datetime.now().isoformat()}")
    print(f"  总耗时: {total_time:.1f}s")
    print()
    print(f"  ┌──────────────────────────────────────────────────┐")
    print(f"  │ 总LLM调用:    {total_calls:>8,}                             │")
    print(f"  │ 总成功:       {total_ok:>8,}                             │")
    print(f"  │ 总成功率:     {total_ok/total_calls*100:>7.2f}%                           │")
    print(f"  │ 总吞吐量:     {total_calls/total_time:>7.1f} calls/s                    │")
    print(f"  └──────────────────────────────────────────────────┘")
    print()
    print(f"  Phase 1 — 100轮迭代 (10 agents/轮 = 1000 calls):")
    print(f"    成功率: {phase1_ok/phase1_total*100:.1f}% | 吞吐: {phase1_total/phase1_time:.1f} calls/s")
    print(f"    迭代成功率: min={min(iter_rates)*100:.0f}% max={max(iter_rates)*100:.0f}% avg={statistics.mean(iter_rates)*100:.1f}% std={statistics.stdev(iter_rates)*100:.2f}%")
    print(f"    迭代延迟: min={min(iter_times):.2f}s max={max(iter_times):.2f}s avg={statistics.mean(iter_times):.2f}s")
    print()
    print(f"  Phase 2 — AgentPool 1000 agents (10批×100):")
    print(f"    成功率: {phase2_ok/phase2_total*100:.1f}% | 吞吐: {phase2_total/phase2_time:.1f} agents/s")
    print()
    print(f"  Phase 3 — Pipeline (100轮×10 agents×3 stages = 3000 calls):")
    print(f"    全链路成功: {phase3_full_ok}/1000 agent-stages")
    print(f"    各阶段: 生成={stage_ok['generate']}/1000 审查={stage_ok['review']}/1000 测试={stage_ok['test']}/1000")
    print(f"    吞吐: {3000/phase3_time:.1f} calls/s")
    print()
    print(f"  Phase 4 — 1000 agents一次性并发:")
    print(f"    成功率: {phase4_ok/NUM_AGENTS*100:.1f}% | 吞吐: {NUM_AGENTS/phase4_time:.1f} agents/s")
    print(f"    延迟: P50={p50:.3f}s P90={p90:.3f}s P99={p99:.3f}s Max={pmax:.3f}s")
    print()

    print(f"  迭代稳定性趋势 (每10轮):")
    for block in range(10):
        br = iter_rates[block * 10:(block + 1) * 10]
        if br:
            avg = statistics.mean(br) * 100
            bar = "█" * int(avg / 2) + "░" * (50 - int(avg / 2))
            print(f"    R{block*10+1:3d}-{(block+1)*10:3d}: {avg:5.1f}% |{bar}|")

    print(f"\n  错误统计: {len(all_errors)} errors")
    if all_errors:
        etypes = Counter(e.get("error", "unknown") for e in all_errors)
        for et, cnt in etypes.most_common(10):
            print(f"    {et}: {cnt}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "num_agents": NUM_AGENTS,
        "num_iterations": NUM_ITERATIONS,
        "total_llm_calls": total_calls,
        "total_success": total_ok,
        "total_success_rate": round(total_ok / total_calls * 100, 2),
        "total_time": round(total_time, 1),
        "total_throughput": round(total_calls / total_time, 2),
        "phase1": {"calls": phase1_total, "ok": phase1_ok, "time": round(phase1_time, 1), "rate": round(phase1_ok / phase1_total * 100, 2)},
        "phase2": {"agents": phase2_total, "ok": phase2_ok, "time": round(phase2_time, 1), "rate": round(phase2_ok / phase2_total * 100, 2), "batches": batch_details},
        "phase3": {"full_ok": phase3_full_ok, "stages": stage_ok, "time": round(phase3_time, 1)},
        "phase4": {"agents": NUM_AGENTS, "ok": phase4_ok, "time": round(phase4_time, 1), "rate": round(phase4_ok / NUM_AGENTS * 100, 2), "latency": {"p50": round(p50, 3), "p90": round(p90, 3), "p99": round(p99, 3), "max": round(pmax, 3)}},
        "iteration_results": iteration_results,
        "pipeline_details": pipeline_details,
        "errors": all_errors[:100],
        "error_count": len(all_errors),
    }
    with open("stress_1000agents_100iters_v2_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: stress_1000agents_100iters_v2_report.json")


if __name__ == "__main__":
    asyncio.run(run_stress_test())
