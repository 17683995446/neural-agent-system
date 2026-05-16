#!/usr/bin/env python3
"""
全链路端到端验证 — 并行化100轮迭代
每轮5个LLM调用点 → 5个agent并行 → AgentPool调度
"""
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

os.environ.setdefault("CHEAP_LLM_MODE", "true")

from app.core.cheap_llm_client import CheapLLMClient
from app.core.llm_client import create_llm_client
from app.core.agent_pool import AgentPool, AgentPriority, AgentTask
from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.llm_cache import LLMResponseCache
from app.core.scalability_profile import ScalabilityProfile
from app.core.config import settings


def check_agent_llm(name: str, factory) -> Dict:
    """检测单个agent LLM连通性"""
    start = time.time()
    info = {"agent": name, "connected": False, "time_ms": 0, "model": "", "error": None}
    try:
        c = factory()
        info["model"] = getattr(c, "model", "?")
        info["connected"] = getattr(c, "is_available", False)
        if info["connected"]:
            r = c.complete(messages=[{"role": "user", "content": "OK"}], max_tokens=128)
            info["time_ms"] = (time.time() - start) * 1000
            info["connected"] = r is not None
    except Exception as e:
        info["time_ms"] = (time.time() - start) * 1000
        info["error"] = str(e)[:100]
    return info


def iteration_round(pool: AgentPool, round_id: int) -> Dict:
    """一轮迭代: 5个LLM调用点并行执行"""
    start = time.time()
    agents = ["conv", "fc1", "fc2", "fc3", "output"]
    prompts = {
        "conv": f"[轮{round_id}] 分析代码结构",
        "fc1": f"[轮{round_id}] 生成修改方案",
        "fc2": f"[轮{round_id}] 修改代码",
        "fc3": f"[轮{round_id}] 生成测试",
        "output": f"[轮{round_id}] 生成报告",
    }

    def call_one(agent_name: str) -> Dict:
        c = CheapLLMClient(max_tokens=128)
        t0 = time.time()
        try:
            r = c.complete(messages=[{"role": "user", "content": prompts[agent_name]}], max_tokens=128)
            text = c.get_response_text(r) if r else ""
            return {"agent": agent_name, "ok": bool(r) and bool(text), "time_ms": (time.time() - t0) * 1000, "len": len(text)}
        except Exception as e:
            return {"agent": agent_name, "ok": False, "time_ms": (time.time() - t0) * 1000, "error": str(e)[:80]}

    results = pool.dispatch_simple(call_one, agents)
    elapsed = (time.time() - start) * 1000

    details = {r.result["agent"]: r.result for r in results if r.result}
    llm_ok = sum(1 for r in results if r.result and r.result.get("ok"))

    return {
        "round": round_id,
        "success": llm_ok >= 3,
        "llm_ok": llm_ok,
        "llm_total": 5,
        "time_ms": round(elapsed, 1),
        "details": details,
    }


def main():
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    output_dir = Path(".")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(f"  全链路端到端验证 — {iterations}轮迭代(并行)")
    print("=" * 70)

    report: Dict[str, Any] = {
        "title": f"全链路端到端验证报告 — {iterations}轮迭代",
        "timestamp": datetime.now().isoformat(),
    }

    # ===== Step 1: 配置 =====
    print("\n[1] 配置")
    cfg = {
        "cheap_llm_mode": getattr(settings, "cheap_llm_mode", False),
        "model": settings.default_llm_model,
        "api_base": settings.anthropic_base_url,
        "api_key_set": bool(settings.anthropic_auth_token or settings.openai_api_key),
        "cpu_count": os.cpu_count(),
    }
    report["config"] = cfg
    for k, v in cfg.items():
        print(f"  {k}: {v}")

    # ===== Step 2: Agent LLM连通性 =====
    print("\n[2] Agent LLM连通性检测")
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
    ]

    agent_results = {}
    for name, factory in agents_to_check:
        info = check_agent_llm(name, factory)
        agent_results[name] = info
        s = "✅" if info["connected"] else "❌"
        print(f"  {s} {name}: {info['model']} ({info['time_ms']:.0f}ms)")

    report["agent_llm"] = {"results": agent_results, "connected": sum(1 for v in agent_results.values() if v["connected"]), "total": len(agent_results)}

    # ===== Step 3: 组件功能测试 =====
    print("\n[3] 组件功能测试")
    comp_tests = {}

    # CircuitBreaker
    cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=5)
    for _ in range(2):
        try: cb.call(lambda: 1/0)
        except: pass
    comp_tests["circuit_breaker_opens"] = cb.state == CircuitState.OPEN
    print(f"  {'✅' if comp_tests['circuit_breaker_opens'] else '❌'} CircuitBreaker熔断")

    # Cache
    cache = LLMResponseCache(ttl_seconds=60)
    cache.put([{"r": "u", "c": "t"}], "val")
    comp_tests["cache_hit"] = cache.get([{"r": "u", "c": "t"}]) == "val"
    print(f"  {'✅' if comp_tests['cache_hit'] else '❌'} Cache命中")

    # ScalabilityProfile
    profile = ScalabilityProfile.detect(".")
    comp_tests["cheap_profile"] = profile["_profile"] == "CHEAP_LLM"
    comp_tests["agent_pool_enabled"] = profile.get("enable_agent_pool") is True
    print(f"  {'✅' if comp_tests['cheap_profile'] else '❌'} CHEAP_LLM Profile")
    print(f"  {'✅' if comp_tests['agent_pool_enabled'] else '❌'} AgentPool启用")

    # AgentPool简单并发
    pool_test = AgentPool(max_workers=8)
    res = pool_test.dispatch_simple(lambda x: x * 2, list(range(20)))
    comp_tests["pool_dispatch"] = len(res) == 20
    print(f"  {'✅' if comp_tests['pool_dispatch'] else '❌'} AgentPool分发")

    report["component_tests"] = comp_tests

    # ===== Step 4: 100轮迭代 =====
    print(f"\n[4] {iterations}轮迭代压力测试(并行)")
    pool = AgentPool(max_workers=32)

    all_iters = []
    success = 0
    fail = 0
    total_llm = 0
    total_llm_ok = 0
    agent_stats: Dict[str, Dict] = defaultdict(lambda: {"calls": 0, "ok": 0, "time_ms": []})

    for i in range(iterations):
        result = iteration_round(pool, i + 1)
        all_iters.append(result)

        if result["success"]:
            success += 1
        else:
            fail += 1

        total_llm += result["llm_total"]
        total_llm_ok += result["llm_ok"]

        for agent_name, detail in result["details"].items():
            agent_stats[agent_name]["calls"] += 1
            if detail.get("ok"):
                agent_stats[agent_name]["ok"] += 1
            agent_stats[agent_name]["time_ms"].append(detail.get("time_ms", 0))

        if (i + 1) % 10 == 0:
            recent = all_iters[-10:]
            avg = sum(r["time_ms"] for r in recent) / 10
            print(f"  [{i+1:3d}/{iterations}] ✅={success} ❌={fail} LLM={total_llm_ok}/{total_llm} 均值={avg:.0f}ms")

    import statistics
    times = [r["time_ms"] for r in all_iters]
    time_stats = {
        "mean_ms": round(statistics.mean(times), 1),
        "median_ms": round(statistics.median(times), 1),
        "stdev_ms": round(statistics.stdev(times), 1) if len(times) > 1 else 0,
        "min_ms": round(min(times), 1),
        "max_ms": round(max(times), 1),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 1),
        "total_s": round(sum(times) / 1000, 1),
    }

    agent_summary = {}
    for name, s in agent_stats.items():
        t = s["time_ms"]
        agent_summary[name] = {
            "calls": s["calls"],
            "ok": s["ok"],
            "fail": s["calls"] - s["ok"],
            "success_rate": s["ok"] / max(s["calls"], 1),
            "avg_ms": round(sum(t) / max(len(t), 1), 1),
            "min_ms": round(min(t), 1) if t else 0,
            "max_ms": round(max(t), 1) if t else 0,
        }

    iter_data = {
        "iterations": iterations,
        "success": success,
        "fail": fail,
        "success_rate": success / iterations,
        "total_llm": total_llm,
        "total_llm_ok": total_llm_ok,
        "llm_success_rate": total_llm_ok / max(total_llm, 1),
        "time_stats": time_stats,
        "agent_summary": agent_summary,
    }
    report["iteration"] = iter_data

    print(f"\n  结果: 成功={success}/{iterations} ({success/iterations:.1%})")
    print(f"  LLM: {total_llm_ok}/{total_llm} ({total_llm_ok/max(total_llm,1):.1%})")
    print(f"  均值: {time_stats['mean_ms']:.0f}ms P95: {time_stats['p95_ms']:.0f}ms")

    # ===== Step 5: 生成报告 =====
    print("\n[5] 生成报告")

    md = []
    md.append(f"# {report['title']}\n")
    md.append(f"时间: {report['timestamp']}\n")

    md.append("\n## 1. 环境配置\n")
    for k, v in cfg.items():
        md.append(f"- **{k}**: {v}")

    md.append("\n## 2. Agent LLM连通性\n")
    ar = report["agent_llm"]
    md.append(f"- 连通: {ar['connected']}/{ar['total']}\n")
    md.append("| Agent | 状态 | 模型 | 耗时(ms) | 错误 |")
    md.append("|-------|------|------|----------|------|")
    for n, i in ar["results"].items():
        s = "✅" if i["connected"] else "❌"
        md.append(f"| {n} | {s} | {i['model']} | {i['time_ms']:.0f} | {i.get('error') or '-'} |")

    md.append("\n## 3. 组件测试\n")
    for k, v in comp_tests.items():
        md.append(f"- {'✅' if v else '❌'} **{k}**")

    md.append("\n## 4. 迭代压力测试\n")
    md.append(f"- **轮次**: {iterations}")
    md.append(f"- **成功**: {success} ({success/iterations:.1%})")
    md.append(f"- **失败**: {fail}")
    md.append(f"- **LLM调用**: {total_llm}")
    md.append(f"- **LLM成功**: {total_llm_ok} ({total_llm_ok/max(total_llm,1):.1%})")

    md.append("\n### 耗时统计\n")
    md.append("| 指标 | 值 |")
    md.append("|------|-----|")
    for k, v in time_stats.items():
        md.append(f"| {k} | {v} |")

    md.append("\n### 每Agent活动详情\n")
    md.append("| Agent | 调用 | 成功 | 失败 | 成功率 | 均值(ms) | 最小(ms) | 最大(ms) |")
    md.append("|-------|------|------|------|--------|----------|----------|----------|")
    for n, s in agent_summary.items():
        md.append(
            f"| {n} | {s['calls']} | {s['ok']} | {s['fail']} "
            f"| {s['success_rate']:.1%} | {s['avg_ms']:.0f} | {s['min_ms']:.0f} | {s['max_ms']:.0f} |"
        )

    md.append("\n### 最近20轮详细记录\n")
    md.append("| 轮次 | 结果 | LLM成功 | 耗时(ms) | conv | fc1 | fc2 | fc3 | output |")
    md.append("|------|------|---------|----------|------|-----|-----|-----|--------|")
    for r in all_iters[-20:]:
        s = "✅" if r["success"] else "❌"
        d = r["details"]
        def agent_s(name):
            a = d.get(name, {})
            return "✅" if a.get("ok") else "❌"
        md.append(f"| {r['round']} | {s} | {r['llm_ok']}/{r['llm_total']} | {r['time_ms']:.0f} | {agent_s('conv')} | {agent_s('fc1')} | {agent_s('fc2')} | {agent_s('fc3')} | {agent_s('output')} |")

    overall = all(v for v in comp_tests.values()) and (success / iterations >= 0.9) and (ar["connected"] >= ar["total"] - 2)
    md.append("\n## 5. 总结\n")
    md.append(f"**{'✅ 验证通过' if overall else '⚠️ 存在问题'}**\n")
    md.append(f"- 组件测试: {'✅ 全部通过' if all(v for v in comp_tests.values()) else '❌ 有失败'}")
    md.append(f"- Agent LLM连通: {ar['connected']}/{ar['total']}")
    md.append(f"- 迭代成功率: {success/iterations:.1%}")
    md.append(f"- LLM成功率: {total_llm_ok/max(total_llm,1):.1%}")
    md.append(f"- 吞吐: {iterations/max(time_stats['total_s'],1):.1f}轮/s")

    report_file = output_dir / f"E2E_REPORT_{ts}.md"
    report_file.write_text("\n".join(md), encoding="utf-8")
    json_file = output_dir / f"e2e_data_{ts}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n报告: {report_file}")
    print(f"数据: {json_file}")
    return report


if __name__ == "__main__":
    main()
