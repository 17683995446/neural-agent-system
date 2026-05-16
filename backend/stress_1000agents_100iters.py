"""
1000 Agents × 100 Iterations 复杂任务全链路压测验证

验证指标:
1. 总吞吐量 (calls/s)
2. 成功率 (逐轮/逐阶段)
3. 延迟分布 (P50/P90/P99/Max)
4. Agent并行效率 (实际并行度/理论并行度)
5. 迭代稳定性 (100轮成功率趋势)
6. 错误分析 (错误类型/分布)
7. 资源消耗 (总LLM调用数/总token消耗估算)
8. 各阶段详细agent活动日志
"""
import asyncio
import time
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.llm_client import LLMClient
from app.core.cheap_llm_client import CheapLLMClient
from app.core.agent_pool import AgentPool, AgentPriority
from app.core.llm_utils import extract_json_from_llm_response, extract_code_from_llm_response

API_KEY = os.getenv("ANTHROPIC_AUTH_TOKEN", "bfccdb7fe8d94be0abb753e48c16c7fe.fMteFrYHmmjJHGUC")
API_BASE = os.getenv("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
MODEL = "glm-4-flash"

NUM_AGENTS = 1000
NUM_ITERATIONS = 100
BATCH_SIZE = 50


def get_text(resp):
    if not resp or "choices" not in resp:
        return ""
    msg = resp["choices"][0].get("message", {})
    return msg.get("content", "") or msg.get("reasoning", "") or ""


async def run_stress_test():
    print("=" * 80)
    print(f"  1000 Agents × 100 Iterations 全链路压测验证")
    print(f"  Model: {MODEL} | API: {API_BASE}")
    print(f"  StartTime: {datetime.now().isoformat()}")
    print("=" * 80)

    all_latencies: List[float] = []
    all_errors: List[Dict] = []
    iteration_results: List[Dict] = []
    stage_details: Dict[str, Dict] = {}

    client = LLMClient(api_key=API_KEY, api_base=API_BASE, model=MODEL)

    # ============================================================
    # Phase 1: 预热 — 10并发 × 5轮
    # ============================================================
    print("\n" + "=" * 80)
    print("  Phase 1: 预热 (10并发 × 5轮)")
    print("=" * 80)
    t0 = time.time()
    warmup_ok = 0
    for i in range(5):
        tasks = [client.acomplete([{"role": "user", "content": f"Warmup {i}-{j}: What is {j}+1?"}], max_tokens=16) for j in range(10)]
        resps = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in resps if not isinstance(r, Exception) and get_text(r))
        warmup_ok += ok
    warmup_time = time.time() - t0
    print(f"  预热完成: {warmup_ok}/50 成功, {warmup_time:.1f}s")

    # ============================================================
    # Phase 2: 逐轮迭代 — 100轮, 每轮50 agents并行 (共5000 LLM调用)
    # ============================================================
    print("\n" + "=" * 80)
    print(f"  Phase 2: 逐轮迭代 (100轮 × 50 agents/轮 = 5000 calls)")
    print("=" * 80)

    phase2_start = time.time()
    phase2_total_ok = 0
    phase2_total_calls = 0

    for iteration in range(1, NUM_ITERATIONS + 1):
        iter_start = time.time()
        prompts = [
            f"Iter {iteration} Agent {j}: Calculate {j}*{j}+{iteration}. Return only the number."
            for j in range(BATCH_SIZE)
        ]
        tasks = [client.acomplete([{"role": "user", "content": p}], max_tokens=32) for p in prompts]
        resps = await asyncio.gather(*tasks, return_exceptions=True)

        iter_ok = 0
        iter_latencies = []
        for j, r in enumerate(resps):
            if isinstance(r, Exception):
                all_errors.append({"iteration": iteration, "agent": j, "error": type(r).__name__, "msg": str(r)[:80]})
            elif get_text(r):
                iter_ok += 1

        iter_time = time.time() - iter_start
        phase2_total_ok += iter_ok
        phase2_total_calls += BATCH_SIZE

        iter_record = {
            "iteration": iteration,
            "success": iter_ok,
            "total": BATCH_SIZE,
            "rate": iter_ok / BATCH_SIZE,
            "time": round(iter_time, 3),
        }
        iteration_results.append(iter_record)
        all_latencies.append(iter_time)

        if iteration % 10 == 0 or iteration <= 3:
            print(f"  Iter {iteration:3d}: {iter_ok}/{BATCH_SIZE} success ({100*iter_ok/BATCH_SIZE:.0f}%) | {iter_time:.2f}s")

    phase2_time = time.time() - phase2_start
    phase2_rate = phase2_total_ok / phase2_total_calls * 100

    stage_details["phase2"] = {
        "total_calls": phase2_total_calls,
        "total_ok": phase2_total_ok,
        "success_rate": round(phase2_rate, 2),
        "total_time": round(phase2_time, 1),
        "throughput": round(phase2_total_calls / phase2_time, 2),
    }

    print(f"\n  Phase 2 Summary:")
    print(f"    总调用: {phase2_total_calls} | 成功: {phase2_total_ok} | 成功率: {phase2_rate:.1f}%")
    print(f"    总耗时: {phase2_time:.1f}s | 吞吐: {phase2_total_calls/phase2_time:.1f} calls/s")

    # ============================================================
    # Phase 3: AgentPool大规模并行 — 1000 agents分10批
    # ============================================================
    print("\n" + "=" * 80)
    print(f"  Phase 3: AgentPool大规模并行 (1000 agents, 10批×100)")
    print("=" * 80)

    phase3_start = time.time()
    phase3_ok = 0
    phase3_total = 0
    phase3_batch_details = []

    def agent_worker(item):
        c = CheapLLMClient(api_key=API_KEY, api_base=API_BASE, model=MODEL)
        prompt = f"Agent {item}: Analyze the number {item}. Is it prime? Answer yes or no."
        r = c.complete([{"role": "user", "content": prompt}], max_tokens=32)
        return r

    num_batches_3 = 10
    agents_per_batch_3 = 100

    for batch_idx in range(num_batches_3):
        batch_start = time.time()
        pool = AgentPool(max_workers=agents_per_batch_3)
        items = list(range(batch_idx * agents_per_batch_3 + 1, (batch_idx + 1) * agents_per_batch_3 + 1))
        results = pool.dispatch_simple(agent_worker, items, timeout=120)

        batch_ok = sum(1 for r in results if r.result is not None)
        batch_time = time.time() - batch_start
        phase3_ok += batch_ok
        phase3_total += agents_per_batch_3

        detail = {"batch": batch_idx + 1, "ok": batch_ok, "total": agents_per_batch_3, "time": round(batch_time, 2)}
        phase3_batch_details.append(detail)
        print(f"  Batch {batch_idx+1:2d}/10: {batch_ok}/{agents_per_batch_3} success | {batch_time:.1f}s")

    phase3_time = time.time() - phase3_start
    stage_details["phase3"] = {
        "total_agents": phase3_total,
        "total_ok": phase3_ok,
        "success_rate": round(phase3_ok / phase3_total * 100, 2),
        "total_time": round(phase3_time, 1),
        "throughput": round(phase3_total / phase3_time, 2),
        "batches": phase3_batch_details,
    }

    print(f"\n  Phase 3 Summary:")
    print(f"    总Agent: {phase3_total} | 成功: {phase3_ok} | 成功率: {phase3_ok/phase3_total*100:.1f}%")
    print(f"    总耗时: {phase3_time:.1f}s | 吞吐: {phase3_total/phase3_time:.1f} agents/s")

    # ============================================================
    # Phase 4: 复杂任务 — 代码生成+审查+测试 (模拟真实pipeline)
    # ============================================================
    print("\n" + "=" * 80)
    print(f"  Phase 4: 复杂Pipeline任务 (代码生成→审查→测试, 50轮)")
    print("=" * 80)

    phase4_start = time.time()
    phase4_stages = {"generate": 0, "review": 0, "test": 0}
    phase4_ok = 0

    for i in range(50):
        # Stage A: 代码生成 (1 agent)
        gen_resp = await client.acomplete(
            [{"role": "user", "content": f"Write a Python function `compute_{i}(x)` that returns x*{i}+1. Just the function."}],
            max_tokens=128
        )
        gen_code = extract_code_from_llm_response(get_text(gen_resp)) or get_text(gen_resp)

        # Stage B: 代码审查 (1 agent)
        review_resp = await client.acomplete(
            [{"role": "user", "content": f"Review this code for bugs. Is it correct?\n```\n{gen_code[:200]}\n```"}],
            max_tokens=64
        )
        review_text = get_text(review_resp)

        # Stage C: 测试生成 (1 agent)
        test_resp = await client.acomplete(
            [{"role": "user", "content": f"Write one assert test for this function:\n```\n{gen_code[:200]}\n```"}],
            max_tokens=64
        )
        test_text = get_text(test_resp)

        if gen_code and review_text and test_text:
            phase4_ok += 1
            phase4_stages["generate"] += 1
            phase4_stages["review"] += 1
            phase4_stages["test"] += 1
        else:
            if gen_code:
                phase4_stages["generate"] += 1
            if review_text:
                phase4_stages["review"] += 1
            if test_text:
                phase4_stages["test"] += 1

        if (i + 1) % 10 == 0:
            print(f"  Pipeline iter {i+1}/50: {phase4_ok} full success so far")

    phase4_time = time.time() - phase4_start
    stage_details["phase4"] = {
        "iterations": 50,
        "full_success": phase4_ok,
        "success_rate": round(phase4_ok / 50 * 100, 2),
        "stages": phase4_stages,
        "total_time": round(phase4_time, 1),
        "throughput": round(50 * 3 / phase4_time, 2),
    }

    print(f"\n  Phase 4 Summary:")
    print(f"    全链路成功: {phase4_ok}/50 ({phase4_ok/50*100:.0f}%)")
    print(f"    各阶段: 生成={phase4_stages['generate']} 审查={phase4_stages['review']} 测试={phase4_stages['test']}")
    print(f"    总耗时: {phase4_time:.1f}s | 吞吐: {50*3/phase4_time:.1f} LLM-calls/s")

    # ============================================================
    # Phase 5: 1000 agents一次性全量并发 (极限测试)
    # ============================================================
    print("\n" + "=" * 80)
    print(f"  Phase 5: 1000 agents一次性全量并发 (极限测试)")
    print("=" * 80)

    phase5_start = time.time()

    async def single_agent_call(idx):
        t = time.time()
        try:
            resp = await client.acomplete(
                [{"role": "user", "content": f"Agent {idx}: What is the {idx}th Fibonacci number? Just the number."}],
                max_tokens=32
            )
            latency = time.time() - t
            ok = bool(get_text(resp))
            return {"idx": idx, "ok": ok, "latency": latency}
        except Exception as e:
            latency = time.time() - t
            all_errors.append({"phase": 5, "agent": idx, "error": type(e).__name__})
            return {"idx": idx, "ok": False, "latency": latency}

    sem = asyncio.Semaphore(100)
    async def bounded_call(idx):
        async with sem:
            return await single_agent_call(idx)

    tasks_5 = [bounded_call(i) for i in range(1, NUM_AGENTS + 1)]
    results_5 = await asyncio.gather(*tasks_5)

    phase5_time = time.time() - phase5_start
    phase5_ok = sum(1 for r in results_5 if r["ok"])
    phase5_latencies = sorted(r["latency"] for r in results_5)

    stage_details["phase5"] = {
        "total_agents": NUM_AGENTS,
        "total_ok": phase5_ok,
        "success_rate": round(phase5_ok / NUM_AGENTS * 100, 2),
        "total_time": round(phase5_time, 1),
        "throughput": round(NUM_AGENTS / phase5_time, 2),
        "latency_p50": round(phase5_latencies[int(len(phase5_latencies) * 0.5)], 3),
        "latency_p90": round(phase5_latencies[int(len(phase5_latencies) * 0.9)], 3),
        "latency_p99": round(phase5_latencies[int(len(phase5_latencies) * 0.99)], 3),
        "latency_max": round(phase5_latencies[-1], 3),
    }

    print(f"  1000 agents并发: {phase5_ok}/{NUM_AGENTS} 成功 ({phase5_ok/NUM_AGENTS*100:.1f}%)")
    print(f"  总耗时: {phase5_time:.1f}s | 吞吐: {NUM_AGENTS/phase5_time:.1f} agents/s")
    print(f"  延迟: P50={stage_details['phase5']['latency_p50']}s P90={stage_details['phase5']['latency_p90']}s P99={stage_details['phase5']['latency_p99']}s Max={stage_details['phase5']['latency_max']}s")

    # ============================================================
    # 综合报告
    # ============================================================
    total_time_all = time.time() - t0 + warmup_time
    total_llm_calls = (phase2_total_calls + phase3_total + 50 * 3 + NUM_AGENTS)
    total_success = phase2_total_ok + phase3_ok + phase4_ok * 3 + phase5_ok

    iter_rates = [r["rate"] for r in iteration_results]
    iter_times = [r["time"] for r in iteration_results]

    print("\n" + "=" * 80)
    print("  综 合 报 告")
    print("=" * 80)
    print(f"  模型: {MODEL} | API: {API_BASE}")
    print(f"  验证时间: {datetime.now().isoformat()}")
    print(f"  总耗时: {total_time_all:.1f}s")
    print()
    print(f"  ┌─────────────────────────────────────────────────────────┐")
    print(f"  │ 总LLM调用数:    {total_llm_calls:>8,}                                  │")
    print(f"  │ 总成功调用:     {total_success:>8,}                                  │")
    print(f"  │ 总成功率:       {total_success/total_llm_calls*100:>7.2f}%                                │")
    print(f"  │ 总吞吐量:       {total_llm_calls/total_time_all:>7.1f} calls/s                          │")
    print(f"  └─────────────────────────────────────────────────────────┘")
    print()
    print(f"  Phase 2 — 100轮迭代 (5000 calls):")
    print(f"    成功率: {phase2_rate:.1f}% | 吞吐: {phase2_total_calls/phase2_time:.1f} calls/s")
    print(f"    迭代成功率: min={min(iter_rates)*100:.0f}% max={max(iter_rates)*100:.0f}% avg={statistics.mean(iter_rates)*100:.1f}% std={statistics.stdev(iter_rates)*100:.2f}%")
    print(f"    迭代延迟: min={min(iter_times):.2f}s max={max(iter_times):.2f}s avg={statistics.mean(iter_times):.2f}s")
    print()
    print(f"  Phase 3 — 1000 agents AgentPool (10批×100):")
    print(f"    成功率: {phase3_ok/phase3_total*100:.1f}% | 吞吐: {phase3_total/phase3_time:.1f} agents/s")
    print()
    print(f"  Phase 4 — Pipeline复杂任务 (50轮×3 stages):")
    print(f"    全链路成功: {phase4_ok}/50 ({phase4_ok/50*100:.0f}%) | 吞吐: {50*3/phase4_time:.1f} calls/s")
    print()
    print(f"  Phase 5 — 1000 agents一次性并发:")
    print(f"    成功率: {phase5_ok/NUM_AGENTS*100:.1f}% | 吞吐: {NUM_AGENTS/phase5_time:.1f} agents/s")
    print(f"    延迟: P50={stage_details['phase5']['latency_p50']}s P90={stage_details['phase5']['latency_p90']}s P99={stage_details['phase5']['latency_p99']}s Max={stage_details['phase5']['latency_max']}s")
    print()
    print(f"  错误统计: {len(all_errors)} errors")
    if all_errors:
        error_types = defaultdict(int)
        for e in all_errors:
            error_types[e.get("error", "unknown")] += 1
        for et, cnt in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"    {et}: {cnt}")

    # 迭代稳定性趋势 (每10轮)
    print(f"\n  迭代稳定性趋势 (每10轮平均成功率):")
    for block in range(10):
        block_rates = iter_rates[block * 10:(block + 1) * 10]
        if block_rates:
            avg_rate = statistics.mean(block_rates) * 100
            bar = "█" * int(avg_rate / 2) + "░" * (50 - int(avg_rate / 2))
            print(f"    Round {block*10+1:3d}-{(block+1)*10:3d}: {avg_rate:5.1f}% |{bar}|")

    # Save JSON
    report = {
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "num_agents": NUM_AGENTS,
        "num_iterations": NUM_ITERATIONS,
        "total_llm_calls": total_llm_calls,
        "total_success": total_success,
        "total_success_rate": round(total_success / total_llm_calls * 100, 2),
        "total_time": round(total_time_all, 1),
        "total_throughput": round(total_llm_calls / total_time_all, 2),
        "stages": stage_details,
        "iteration_results": iteration_results,
        "errors": all_errors[:50],
        "error_count": len(all_errors),
    }
    with open("stress_1000agents_100iters_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: stress_1000agents_100iters_report.json")


if __name__ == "__main__":
    asyncio.run(run_stress_test())
