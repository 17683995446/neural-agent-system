"""
1000 Agents × 100 Iterations 全链路压测 (v3)
分阶段执行，每阶段独立保存，适配GLM-4-Flash限流
"""
import asyncio
import time
import json
import os
import statistics
from collections import Counter
from datetime import datetime
from typing import Dict, List

from app.core.cheap_llm_client import CheapLLMClient
from app.core.agent_pool import AgentPool
from app.core.llm_utils import extract_code_from_llm_response

API_KEY = os.getenv("ANTHROPIC_AUTH_TOKEN", "bfccdb7fe8d94be0abb753e48c16c7fe.fMteFrYHmmjJHGUC")
API_BASE = os.getenv("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
MODEL = "glm-4-flash"

def get_text(resp):
    if not resp or "choices" not in resp:
        return ""
    msg = resp["choices"][0].get("message", {})
    return msg.get("content", "") or msg.get("reasoning", "") or ""

def make_cheap():
    return CheapLLMClient(api_key=API_KEY, api_base=API_BASE, model=MODEL)

async def acheap(prompt, max_tokens=32):
    c = make_cheap()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: c.complete([{"role":"user","content":prompt}], max_tokens=max_tokens))


async def phase1_iterations():
    """100轮迭代, 每轮10 agents, 共1000 calls"""
    print("\n" + "=" * 70)
    print("  Phase 1: 100轮迭代 (10 agents/轮 = 1000 calls)")
    print("=" * 70)
    start = time.time()
    results = []
    errors = []
    total_ok = 0

    for i in range(1, 101):
        t0 = time.time()
        resps = await asyncio.gather(*[
            acheap(f"Iter {i} Agent {j}: Compute {j}*{j}+{i}. Just the number.")
            for j in range(10)
        ])
        ok = sum(1 for r in resps if r and get_text(r))
        fail = sum(1 for r in resps if r is None)
        total_ok += ok
        elapsed = time.time() - t0
        results.append({"iter": i, "ok": ok, "fail_none": fail, "time": round(elapsed, 3)})
        if i % 20 == 0 or i <= 3:
            print(f"  Iter {i:3d}: {ok}/10 ok (None={fail}) | {elapsed:.2f}s")

    total_time = time.time() - start
    print(f"  >>> Phase 1: {total_ok}/1000 success ({total_ok/10:.1f}%) | {total_time:.1f}s | {1000/total_time:.1f} calls/s")
    return {"ok": total_ok, "total": 1000, "time": round(total_time, 1), "results": results}


async def phase2_agentpool():
    """1000 agents via AgentPool, 10 batches × 100"""
    print("\n" + "=" * 70)
    print("  Phase 2: AgentPool 1000 agents (10批×100)")
    print("=" * 70)
    start = time.time()
    total_ok = 0
    batches = []

    def agent_fn(item):
        c = make_cheap()
        return c.complete([{"role":"user","content":f"Agent {item}: Is {item} prime? Answer yes/no."}], max_tokens=32)

    for b in range(10):
        t0 = time.time()
        pool = AgentPool(max_workers=100)
        items = list(range(b*100+1, (b+1)*100+1))
        res = pool.dispatch_simple(agent_fn, items, timeout=120)
        bok = sum(1 for r in res if r.result is not None)
        bt = time.time() - t0
        total_ok += bok
        batches.append({"batch": b+1, "ok": bok, "time": round(bt, 2)})
        print(f"  Batch {b+1:2d}: {bok}/100 | {bt:.1f}s")

    total_time = time.time() - start
    print(f"  >>> Phase 2: {total_ok}/1000 success ({total_ok/10:.1f}%) | {total_time:.1f}s | {1000/total_time:.1f} agents/s")
    return {"ok": total_ok, "total": 1000, "time": round(total_time, 1), "batches": batches}


async def phase3_pipeline():
    """100轮 Pipeline (生成→审查→测试), 10 agents/轮, 3000 calls"""
    print("\n" + "=" * 70)
    print("  Phase 3: Pipeline (100轮×10 agents×3 stages = 3000 calls)")
    print("=" * 70)
    start = time.time()
    stage_ok = {"gen": 0, "rev": 0, "test": 0}
    full_ok = 0

    for i in range(1, 101):
        t0 = time.time()
        gen = await asyncio.gather(*[acheap(f"Write function f_{j}(x)=x*{j}+{i}. Just the function.", max_tokens=128) for j in range(10)])
        gok = sum(1 for r in gen if r and get_text(r))
        codes = [extract_code_from_llm_response(get_text(r)) or get_text(r) for r in gen]
        rev = await asyncio.gather(*[acheap(f"Is this code correct?\n```\n{(c or '')[:120]}\n```", max_tokens=32) for c in codes])
        rok = sum(1 for r in rev if r and get_text(r))
        tst = await asyncio.gather(*[acheap(f"Write one assert for:\n```\n{(c or '')[:120]}\n```", max_tokens=64) for c in codes])
        tok = sum(1 for r in tst if r and get_text(r))
        stage_ok["gen"] += gok
        stage_ok["rev"] += rok
        stage_ok["test"] += tok
        full_ok += min(gok, rok, tok)
        if i % 20 == 0 or i <= 3:
            print(f"  Pipeline {i:3d}: gen={gok} rev={rok} test={tok} | {time.time()-t0:.1f}s")

    total_time = time.time() - start
    print(f"  >>> Phase 3: full={full_ok}/1000 gen={stage_ok['gen']} rev={stage_ok['rev']} test={stage_ok['test']} | {total_time:.1f}s | {3000/total_time:.1f} calls/s")
    return {"full_ok": full_ok, "stages": stage_ok, "time": round(total_time, 1)}


async def phase4_1000_concurrent():
    """1000 agents 一次性并发, Semaphore=10限流"""
    print("\n" + "=" * 70)
    print("  Phase 4: 1000 agents并发 (Semaphore=10)")
    print("=" * 70)
    start = time.time()
    sem = asyncio.Semaphore(10)
    latencies = []
    ok_count = 0
    none_count = 0

    async def agent(idx):
        nonlocal ok_count, none_count
        async with sem:
            t0 = time.time()
            r = await acheap(f"Agent {idx}: Fib({idx}) mod 100? Just number.")
            lat = time.time() - t0
            if r and get_text(r):
                ok_count += 1
            elif r is None:
                none_count += 1
            return lat

    lats = await asyncio.gather(*[agent(i) for i in range(1, 1001)])
    latencies = sorted(lats)

    total_time = time.time() - start
    p50 = latencies[500]
    p90 = latencies[900]
    p99 = latencies[990]
    pmax = latencies[-1]
    print(f"  >>> Phase 4: {ok_count}/1000 success (None={none_count}) | {total_time:.1f}s | {1000/total_time:.1f} agents/s")
    print(f"      Latency: P50={p50:.3f}s P90={p90:.3f}s P99={p99:.3f}s Max={pmax:.3f}s")
    return {"ok": ok_count, "none": none_count, "time": round(total_time, 1),
            "latency": {"p50": round(p50,3), "p90": round(p90,3), "p99": round(p99,3), "max": round(pmax,3)}}


async def main():
    print("=" * 70)
    print("  1000 Agents × 100 Iterations 全链路压测 (v3)")
    print(f"  Model: {MODEL} | Time: {datetime.now().isoformat()}")
    print("=" * 70)

    total_start = time.time()

    p1 = await phase1_iterations()
    p2 = await phase2_agentpool()
    p3 = await phase3_pipeline()
    p4 = await phase4_1000_concurrent()

    total_time = time.time() - total_start
    total_calls = 1000 + 1000 + 3000 + 1000
    total_ok = p1["ok"] + p2["ok"] + sum(p3["stages"].values()) + p4["ok"]

    # 综合报告
    iters = p1["results"]
    rates = [r["ok"] / 10 for r in iters]
    times = [r["time"] for r in iters]

    print("\n" + "=" * 70)
    print("  综 合 报 告")
    print("=" * 70)
    print(f"  模型: {MODEL} | 总耗时: {total_time:.1f}s")
    print(f"  总LLM调用: {total_calls:,} | 总成功: {total_ok:,} | 成功率: {total_ok/total_calls*100:.2f}%")
    print(f"  总吞吐: {total_calls/total_time:.1f} calls/s")
    print()
    print(f"  Phase 1 (100轮迭代): {p1['ok']}/1000 ({p1['ok']/10:.1f}%) | {1000/p1['time']:.1f} calls/s")
    print(f"    迭代率: min={min(rates)*100:.0f}% max={max(rates)*100:.0f}% avg={statistics.mean(rates)*100:.1f}% std={statistics.stdev(rates)*100:.2f}%")
    print(f"    迭代延迟: min={min(times):.2f}s max={max(times):.2f}s avg={statistics.mean(times):.2f}s")
    print()
    print(f"  Phase 2 (AgentPool 1000): {p2['ok']}/1000 ({p2['ok']/10:.1f}%) | {1000/p2['time']:.1f} agents/s")
    print()
    print(f"  Phase 3 (Pipeline 3000): full={p3['full_ok']}/1000 gen={p3['stages']['gen']} rev={p3['stages']['rev']} test={p3['stages']['test']} | {3000/p3['time']:.1f} calls/s")
    print()
    print(f"  Phase 4 (1000并发): {p4['ok']}/1000 ({p4['ok']/10:.1f}%) | {1000/p4['time']:.1f} agents/s")
    print(f"    延迟: P50={p4['latency']['p50']}s P90={p4['latency']['p90']}s P99={p4['latency']['p99']}s Max={p4['latency']['max']}s")
    print()

    print("  迭代稳定性趋势 (每10轮):")
    for b in range(10):
        br = rates[b*10:(b+1)*10]
        if br:
            avg = statistics.mean(br) * 100
            bar = "█" * int(avg / 2) + "░" * (50 - int(avg / 2))
            print(f"    R{b*10+1:3d}-{(b+1)*10:3d}: {avg:5.1f}% |{bar}|")

    report = {
        "timestamp": datetime.now().isoformat(), "model": MODEL,
        "total_calls": total_calls, "total_ok": total_ok,
        "success_rate": round(total_ok/total_calls*100, 2),
        "total_time": round(total_time, 1),
        "throughput": round(total_calls/total_time, 2),
        "phase1": p1, "phase2": p2, "phase3": p3, "phase4": p4,
    }
    with open("stress_1000agents_100iters_v3_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: stress_1000agents_100iters_v3_report.json")

if __name__ == "__main__":
    asyncio.run(main())
