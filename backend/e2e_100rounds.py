#!/usr/bin/env python3
"""
全链路100轮迭代验证 — 全量并行dispatch
100轮×5个agent=500次LLM调用 → 一次性dispatch到32 worker → 并行执行
预计耗时: 500×6s/32workers ≈ 94s
"""
import json
import os
import sys
import time
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

os.environ.setdefault("CHEAP_LLM_MODE", "true")

from app.core.cheap_llm_client import CheapLLMClient
from app.core.llm_client import create_llm_client
from app.core.agent_pool import AgentPool, AgentPriority, AgentTask, AgentResult
from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.llm_cache import LLMResponseCache
from app.core.scalability_profile import ScalabilityProfile
from app.core.config import settings


def check_llm(name: str, factory) -> Dict:
    start = time.time()
    info = {"agent": name, "connected": False, "time_ms": 0, "model": "", "error": None, "text": ""}
    try:
        c = factory()
        info["model"] = getattr(c, "model", "?")
        info["connected"] = getattr(c, "is_available", False)
        if info["connected"]:
            r = c.complete(messages=[{"role": "user", "content": "回复OK"}], max_tokens=128)
            info["time_ms"] = (time.time() - start) * 1000
            info["connected"] = r is not None
            info["text"] = (c.get_response_text(r) if r else "")[:50]
    except Exception as e:
        info["time_ms"] = (time.time() - start) * 1000
        info["error"] = str(e)[:100]
    return info


def main():
    iterations = 100
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(f"  全链路端到端验证 — {iterations}轮迭代(全量并行)")
    print("=" * 70)

    report: Dict[str, Any] = {"title": f"全链路端到端验证报告 — {iterations}轮迭代", "timestamp": datetime.now().isoformat()}

    # ===== Step 1: 配置 =====
    print("\n[1] 环境配置")
    cfg = {
        "cheap_llm_mode": getattr(settings, "cheap_llm_mode", False),
        "model": settings.default_llm_model,
        "api_base": settings.anthropic_base_url,
        "api_key_set": bool(settings.anthropic_auth_token or settings.openai_api_key),
        "cpu_count": os.cpu_count(),
        "pool_workers": 32,
    }
    report["config"] = cfg
    for k, v in cfg.items():
        print(f"  {k}: {v}")

    # ===== Step 2: Agent LLM连通性 =====
    print("\n[2] 每Agent LLM连通性检测(并行)")
    agents_to_check = [
        ("卷积-CheapLLM", lambda: CheapLLMClient()),
        ("池化-CheapLLM", lambda: CheapLLMClient()),
        ("FC1-CheapLLM", lambda: CheapLLMClient()),
        ("FC2-CheapLLM", lambda: CheapLLMClient()),
        ("FC3-CheapLLM", lambda: CheapLLMClient()),
        ("输出-CheapLLM", lambda: CheapLLMClient()),
        ("反向传播-CheapLLM", lambda: CheapLLMClient()),
        ("卷积-普通LLM", lambda: create_llm_client()),
        ("FC1-普通LLM", lambda: create_llm_client()),
        ("FC2-普通LLM", lambda: create_llm_client()),
        ("FC3-普通LLM", lambda: create_llm_client()),
        ("反向传播-普通LLM", lambda: create_llm_client()),
    ]

    check_pool = AgentPool(max_workers=12)
    check_results_raw = check_pool.dispatch_simple(
        lambda item: check_llm(item[0], item[1]), agents_to_check
    )
    agent_results = {}
    for r in check_results_raw:
        if r.result:
            name = r.result["agent"]
            agent_results[name] = r.result
            s = "✅" if r.result["connected"] else "❌"
            print(f"  {s} {name}: {r.result['model']} ({r.result['time_ms']:.0f}ms)")

    connected_count = sum(1 for v in agent_results.values() if v["connected"])
    report["agent_llm"] = {"results": agent_results, "connected": connected_count, "total": len(agents_to_check)}

    # ===== Step 3: 组件测试 =====
    print("\n[3] 组件功能测试")
    comp = {}

    cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=5)
    for _ in range(2):
        try: cb.call(lambda: 1/0)
        except: pass
    comp["circuit_breaker_opens"] = cb.state == CircuitState.OPEN
    cb.reset()
    comp["circuit_breaker_resets"] = cb.state == CircuitState.CLOSED

    cache = LLMResponseCache(ttl_seconds=60)
    cache.put([{"r": "u", "c": "t"}], "val")
    comp["cache_hit"] = cache.get([{"r": "u", "c": "t"}]) == "val"
    comp["cache_miss"] = cache.get([{"r": "u", "c": "x"}]) is None

    profile = ScalabilityProfile.detect(".")
    comp["cheap_profile"] = profile["_profile"] == "CHEAP_LLM"
    comp["agent_pool_enabled"] = profile.get("enable_agent_pool") is True
    comp["high_qps"] = profile["llm_max_qps"] >= 999
    comp["high_concurrent"] = profile["llm_max_concurrent"] >= 999

    pool_test = AgentPool(max_workers=8)
    res = pool_test.dispatch_simple(lambda x: x * 2, list(range(20)))
    comp["pool_dispatch"] = len(res) == 20 and all(r.error is None for r in res)

    for k, v in comp.items():
        print(f"  {'✅' if v else '❌'} {k}")
    report["component_tests"] = comp

    # ===== Step 4: 100轮迭代(全量并行) =====
    print(f"\n[4] {iterations}轮迭代压力测试 — 全量并行dispatch")
    print(f"  总LLM调用: {iterations}轮 × 5层 = {iterations * 5}次")
    print(f"  并发workers: 32")
    print(f"  预计耗时: ~{iterations * 5 * 6 / 32:.0f}s")

    agents = ["conv", "fc1", "fc2", "fc3", "output"]
    prompts = {}
    for i in range(iterations):
        for agent in agents:
            task_key = f"{i:03d}_{agent}"
            prompts[task_key] = f"[轮{i+1}] {agent}层执行任务"

    all_keys = list(prompts.keys())
    total_calls = len(all_keys)
    print(f"  实际dispatch: {total_calls}个任务")

    pool = AgentPool(max_workers=8)

    completed_count = [0]
    total_count = [total_calls]

    def on_progress(done, total):
        completed_count[0] = done
        if done % 50 == 0 or done == total:
            print(f"    进度: {done}/{total} ({done/total:.0%})")

    t_start = time.time()

    def call_llm(key: str) -> Dict:
        c = CheapLLMClient(max_tokens=128)
        prompt = prompts[key]
        t0 = time.time()
        try:
            r = c.complete(messages=[{"role": "user", "content": prompt}], max_tokens=128)
            text = c.get_response_text(r) if r else ""
            elapsed = (time.time() - t0) * 1000
            return {"key": key, "ok": bool(r) and bool(text), "time_ms": round(elapsed, 1), "text_len": len(text)}
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            return {"key": key, "ok": False, "time_ms": round(elapsed, 1), "error": str(e)[:80]}

    all_results = pool.dispatch_simple(call_llm, all_keys, on_progress=on_progress)
    total_elapsed = (time.time() - t_start) * 1000

    print(f"\n  全量dispatch完成! 耗时: {total_elapsed/1000:.1f}s")

    # 分析结果
    iter_data = defaultdict(lambda: {"agents": {}, "llm_ok": 0, "llm_total": 0})
    agent_stats = defaultdict(lambda: {"calls": 0, "ok": 0, "fail": 0, "times": []})

    for r in all_results:
        if r.result is None:
            continue
        d = r.result
        key = d["key"]
        parts = key.split("_", 1)
        iter_id = int(parts[0])
        agent_name = parts[1]

        iter_data[iter_id]["agents"][agent_name] = d
        iter_data[iter_id]["llm_total"] += 1
        if d["ok"]:
            iter_data[iter_id]["llm_ok"] += 1

        agent_stats[agent_name]["calls"] += 1
        if d["ok"]:
            agent_stats[agent_name]["ok"] += 1
        else:
            agent_stats[agent_name]["fail"] += 1
        agent_stats[agent_name]["times"].append(d.get("time_ms", 0))

    # 计算每轮成功与否
    iter_results = []
    success_count = 0
    fail_count = 0
    for i in range(iterations):
        data = iter_data[i]
        round_ok = data["llm_ok"] >= 3
        if round_ok:
            success_count += 1
        else:
            fail_count += 1
        iter_results.append({
            "round": i + 1,
            "success": round_ok,
            "llm_ok": data["llm_ok"],
            "llm_total": data["llm_total"],
            "agents": {k: {"ok": v["ok"], "time_ms": v.get("time_ms", 0)} for k, v in data["agents"].items()},
        })

    total_llm = sum(d["llm_total"] for d in iter_data.values())
    total_llm_ok = sum(d["llm_ok"] for d in iter_data.values())

    # 每轮耗时(取该轮最长agent耗时)
    round_times = []
    for i in range(iterations):
        data = iter_data[i]
        max_t = max((v.get("time_ms", 0) for v in data["agents"].values()), default=0)
        round_times.append(max_t)

    agent_summary = {}
    for name, s in agent_stats.items():
        t = s["times"]
        agent_summary[name] = {
            "calls": s["calls"],
            "ok": s["ok"],
            "fail": s["fail"],
            "success_rate": s["ok"] / max(s["calls"], 1),
            "avg_ms": round(sum(t) / max(len(t), 1), 1),
            "min_ms": round(min(t), 1) if t else 0,
            "max_ms": round(max(t), 1) if t else 0,
            "median_ms": round(statistics.median(t), 1) if t else 0,
            "p95_ms": round(sorted(t)[int(len(t) * 0.95)], 1) if len(t) > 5 else 0,
        }

    iter_report = {
        "iterations": iterations,
        "success": success_count,
        "fail": fail_count,
        "success_rate": success_count / iterations,
        "total_llm_calls": total_llm,
        "total_llm_ok": total_llm_ok,
        "llm_success_rate": total_llm_ok / max(total_llm, 1),
        "total_elapsed_s": round(total_elapsed / 1000, 1),
        "throughput_calls_per_s": round(total_llm / (total_elapsed / 1000), 1),
        "throughput_rounds_per_s": round(iterations / (total_elapsed / 1000), 2),
        "round_time_stats": {
            "mean_ms": round(statistics.mean(round_times), 1) if round_times else 0,
            "median_ms": round(statistics.median(round_times), 1) if round_times else 0,
            "p95_ms": round(sorted(round_times)[int(len(round_times) * 0.95)], 1) if len(round_times) > 5 else 0,
        },
        "agent_summary": agent_summary,
    }
    report["iteration"] = iter_report

    print(f"\n  迭代结果:")
    print(f"    成功: {success_count}/{iterations} ({success_count/iterations:.1%})")
    print(f"    LLM成功: {total_llm_ok}/{total_llm} ({total_llm_ok/max(total_llm,1):.1%})")
    print(f"    总耗时: {total_elapsed/1000:.1f}s")
    print(f"    吞吐: {iter_report['throughput_calls_per_s']:.1f} calls/s, {iter_report['throughput_rounds_per_s']:.2f} rounds/s")

    # ===== Step 5: 生成报告 =====
    print("\n[5] 生成报告")

    md = []
    md.append(f"# {report['title']}\n")
    md.append(f"生成时间: {report['timestamp']}\n")

    md.append("\n## 1. 环境配置\n")
    for k, v in cfg.items():
        md.append(f"- **{k}**: {v}")

    md.append("\n## 2. 每Agent LLM连通性检测\n")
    ar = report["agent_llm"]
    md.append(f"- **连通**: {ar['connected']}/{ar['total']}\n")
    md.append("| Agent | 状态 | 模型 | 耗时(ms) | 响应 | 错误 |")
    md.append("|-------|------|------|----------|------|------|")
    for n, i in ar["results"].items():
        s = "✅" if i["connected"] else "❌"
        rt = f"{i['time_ms']:.0f}" if i["time_ms"] else "-"
        txt = (i.get("text") or "").replace("\n", " ")[:30]
        err = (i.get("error") or "-")[:40]
        md.append(f"| {n} | {s} | {i['model']} | {rt} | {txt} | {err} |")

    md.append("\n## 3. 组件功能测试\n")
    for k, v in comp.items():
        md.append(f"- {'✅' if v else '❌'} **{k}**")

    md.append("\n## 4. 迭代压力测试(全量并行)\n")
    md.append(f"- **轮次**: {iterations}")
    md.append(f"- **成功**: {success_count} ({success_count/iterations:.1%})")
    md.append(f"- **失败**: {fail_count}")
    md.append(f"- **总LLM调用**: {total_llm}")
    md.append(f"- **LLM成功**: {total_llm_ok} ({total_llm_ok/max(total_llm,1):.1%})")
    md.append(f"- **总耗时**: {iter_report['total_elapsed_s']}s")
    md.append(f"- **吞吐**: {iter_report['throughput_calls_per_s']:.1f} calls/s, {iter_report['throughput_rounds_per_s']:.2f} rounds/s")

    rts = iter_report["round_time_stats"]
    md.append("\n### 每轮耗时(取该轮最长agent)\n")
    md.append("| 指标 | 值 |")
    md.append("|------|-----|")
    for k, v in rts.items():
        md.append(f"| {k} | {v} |")

    md.append("\n### 每Agent活动详情\n")
    md.append("| Agent | 调用 | 成功 | 失败 | 成功率 | 均值(ms) | 中位(ms) | P95(ms) | 最小(ms) | 最大(ms) |")
    md.append("|-------|------|------|------|--------|----------|----------|---------|----------|----------|")
    for n, s in agent_summary.items():
        md.append(
            f"| {n} | {s['calls']} | {s['ok']} | {s['fail']} "
            f"| {s['success_rate']:.1%} | {s['avg_ms']:.0f} | {s['median_ms']:.0f} "
            f"| {s['p95_ms']:.0f} | {s['min_ms']:.0f} | {s['max_ms']:.0f} |"
        )

    # 失败轮次详情
    fail_rounds = [r for r in iter_results if not r["success"]]
    if fail_rounds:
        md.append(f"\n### 失败轮次({len(fail_rounds)}轮)\n")
        for r in fail_rounds:
            agents_detail = " ".join(f"{k}={'✅' if v['ok'] else '❌'}" for k, v in r["agents"].items())
            md.append(f"- 轮{r['round']}: LLM={r['llm_ok']}/{r['llm_total']} | {agents_detail}")
    else:
        md.append("\n### 失败轮次: 无 ✅\n")

    # 最近20轮
    md.append("\n### 最近20轮记录\n")
    md.append("| 轮次 | 结果 | LLM | conv | fc1 | fc2 | fc3 | output |")
    md.append("|------|------|-----|------|-----|-----|-----|--------|")
    for r in iter_results[-20:]:
        s = "✅" if r["success"] else "❌"
        a = r["agents"]
        def as_(n): return "✅" if a.get(n, {}).get("ok") else "❌"
        md.append(f"| {r['round']} | {s} | {r['llm_ok']}/{r['llm_total']} | {as_('conv')} | {as_('fc1')} | {as_('fc2')} | {as_('fc3')} | {as_('output')} |")

    overall = all(v for v in comp.values()) and (success_count / iterations >= 0.95) and (ar["connected"] >= ar["total"] - 2)
    md.append("\n## 5. 总结\n")
    md.append(f"**{'✅ 验证通过' if overall else '⚠️ 存在问题'}**\n")
    conn_str = "✅" if ar["connected"] == ar["total"] else f"❌ ({ar['connected']}/{ar['total']})"
    md.append(f"- Agent LLM全部连通: {conn_str}")
    md.append(f"- 组件测试: {'✅ 全部通过' if all(v for v in comp.values()) else '❌'}")
    md.append(f"- 迭代成功率: {success_count}/{iterations} ({success_count/iterations:.1%})")
    md.append(f"- LLM成功率: {total_llm_ok}/{total_llm} ({total_llm_ok/max(total_llm,1):.1%})")
    md.append(f"- 吞吐: {iter_report['throughput_calls_per_s']:.1f} calls/s")
    md.append(f"- 总耗时: {iter_report['total_elapsed_s']}s")

    report_file = Path(f"FINAL_E2E_100ROUNDS_REPORT.md")
    report_file.write_text("\n".join(md), encoding="utf-8")
    json_file = Path(f"final_e2e_100rounds_data.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n报告: {report_file}")
    print(f"数据: {json_file}")
    return report


if __name__ == "__main__":
    main()
