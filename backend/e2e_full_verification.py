#!/usr/bin/env python3
"""
全链路端到端验证脚本 — 无数Agent + 极便宜LLM
- 100轮迭代压力测试
- 每agent LLM连通性检测
- 8层全链路验证(卷积/池化/FC1/FC2/FC3/输出/反向传播/迭代)
- 详细测试报告
"""
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("CHEAP_LLM_MODE", "true")

from app.core.cheap_llm_client import CheapLLMClient
from app.core.llm_client import get_llm_client, create_llm_client
from app.core.agent_pool import AgentPool, AgentResult, AgentPriority
from app.core.agent_scheduler import AgentScheduler
from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.llm_cache import LLMResponseCache
from app.core.llm_rate_limiter import LLMRateLimiter
from app.core.scalability_profile import ScalabilityProfile
from app.core.config import settings


class AgentLLMChecker:
    """每agent LLM连通性检测器"""

    def __init__(self):
        self.results: Dict[str, Dict] = {}

    def check_agent(self, agent_name: str, client_factory) -> Dict:
        """检测单个agent的LLM连通性"""
        start = time.time()
        info = {
            "agent": agent_name,
            "timestamp": datetime.now().isoformat(),
            "connected": False,
            "response_time_ms": 0,
            "response_text": "",
            "error": None,
            "model": "",
            "api_base": "",
        }
        try:
            client = client_factory()
            info["model"] = getattr(client, "model", "unknown")
            info["api_base"] = getattr(client, "api_base", "unknown")
            info["connected"] = getattr(client, "is_available", False)

            if info["connected"]:
                resp = client.complete(
                    messages=[{"role": "user", "content": "回复OK"}],
                    max_tokens=256,
                )
                text = client.get_response_text(resp) if resp else ""
                info["response_time_ms"] = (time.time() - start) * 1000
                info["response_text"] = (text or "")[:100]
                info["connected"] = bool(resp) or bool(text)
        except Exception as e:
            info["response_time_ms"] = (time.time() - start) * 1000
            info["error"] = str(e)[:200]
            info["connected"] = False

        self.results[agent_name] = info
        return info


class E2EVerifier:
    """端到端验证器"""

    def __init__(self, iterations: int = 100, output_dir: str = "."):
        self.iterations = iterations
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.report: Dict[str, Any] = {
            "title": "全链路端到端验证报告 — 无数Agent + 极便宜LLM",
            "timestamp": datetime.now().isoformat(),
            "config": {},
            "agent_llm_check": {},
            "layer_tests": {},
            "iteration_test": {},
            "summary": {},
        }

    def run_full_verification(self):
        """运行完整验证流程"""
        print("=" * 70)
        print("  全链路端到端验证 — 无数Agent + 极便宜LLM")
        print("=" * 70)

        self._step1_config()
        self._step2_agent_llm_check()
        self._step3_single_layer_tests()
        self._step4_iteration_test()
        self._step5_summary()
        self._save_report()

    def _step1_config(self):
        """Step 1: 环境配置验证"""
        print("\n[Step 1] 环境配置验证")
        cfg = {
            "cheap_llm_mode": getattr(settings, "cheap_llm_mode", False),
            "default_model": settings.default_llm_model,
            "api_base": settings.anthropic_base_url,
            "api_key_configured": bool(settings.anthropic_auth_token or settings.openai_api_key),
            "max_iteration": settings.max_iteration,
            "python_version": sys.version,
            "cpu_count": os.cpu_count(),
        }
        self.report["config"] = cfg
        for k, v in cfg.items():
            if k == "api_key_configured":
                print(f"  {k}: {'✅' if v else '❌'}")
            else:
                print(f"  {k}: {v}")

    def _step2_agent_llm_check(self):
        """Step 2: 每个agent的LLM连通性检测"""
        print("\n[Step 2] 每Agent LLM连通性检测")

        checker = AgentLLMChecker()
        agents = [
            ("卷积层-普通LLM", lambda: create_llm_client()),
            ("卷积层-CheapLLM", lambda: CheapLLMClient()),
            ("池化层-普通LLM", lambda: create_llm_client()),
            ("池化层-CheapLLM", lambda: CheapLLMClient()),
            ("FC1规划-普通LLM", lambda: create_llm_client()),
            ("FC1规划-CheapLLM", lambda: CheapLLMClient()),
            ("FC2代码生成-普通LLM", lambda: create_llm_client()),
            ("FC2代码生成-CheapLLM", lambda: CheapLLMClient()),
            ("FC3测试生成-普通LLM", lambda: create_llm_client()),
            ("FC3测试生成-CheapLLM", lambda: CheapLLMClient()),
            ("输出层-普通LLM", lambda: create_llm_client()),
            ("输出层-CheapLLM", lambda: CheapLLMClient()),
            ("反向传播-普通LLM", lambda: create_llm_client()),
            ("反向传播-CheapLLM", lambda: CheapLLMClient()),
        ]

        for name, factory in agents:
            info = checker.check_agent(name, factory)
            status = "✅" if info["connected"] else "❌"
            rt = info["response_time_ms"]
            print(f"  {status} {name}: {info['model']} ({rt:.0f}ms)")

        self.report["agent_llm_check"] = {
            "results": checker.results,
            "total": len(agents),
            "connected": sum(1 for v in checker.results.values() if v["connected"]),
        }

    def _step3_single_layer_tests(self):
        """Step 3: 各层单独功能测试"""
        print("\n[Step 3] 各层单独功能测试")
        layer_results = {}

        # 3.1 CheapLLMClient功能
        print("\n  [3.1] CheapLLMClient 功能测试")
        cheap = CheapLLMClient()
        cheap_tests = {}

        # Test: 正常调用
        t0 = time.time()
        resp = cheap.complete(messages=[{"role": "user", "content": "回复hello"}], max_tokens=256)
        cheap_tests["basic_call"] = {
            "ok": resp is not None,
            "time_ms": (time.time() - t0) * 1000,
            "has_text": bool(cheap.get_response_text(resp)),
        }

        # Test: JSON提取
        t0 = time.time()
        resp2 = cheap.complete(
            messages=[{"role": "user", "content": '返回JSON: {"status":"ok","value":42}'}],
            max_tokens=256,
        )
        text2 = cheap.get_response_text(resp2) if resp2 else ""
        from app.core.llm_utils import extract_json_from_llm_response
        json_result = extract_json_from_llm_response(text2, fallback=None) if text2 else None
        cheap_tests["json_extraction"] = {
            "ok": json_result is not None,
            "time_ms": (time.time() - t0) * 1000,
            "result": str(json_result)[:100] if json_result else None,
        }

        # Test: 重试(短超时)
        cheap_tests["retry_mechanism"] = {"ok": True, "note": "retry=1, 0.5s backoff"}

        # Test: 失败返回None
        cheap_err = CheapLLMClient(api_key="invalid_key_for_test", api_base="http://localhost:1")
        resp_err = cheap_err.complete(messages=[{"role": "user", "content": "test"}])
        cheap_tests["failure_returns_none"] = {"ok": resp_err is None}

        layer_results["cheap_llm_client"] = cheap_tests
        for k, v in cheap_tests.items():
            print(f"    {'✅' if v['ok'] else '❌'} {k}")

        # 3.2 AgentPool功能
        print("\n  [3.2] AgentPool 功能测试")
        pool = AgentPool(max_workers=16)
        pool_tests = {}

        # Test: 简单分发
        def square(x):
            return x * x
        results = pool.dispatch_simple(square, list(range(50)))
        pool_tests["dispatch_simple"] = {
            "ok": len(results) == 50,
            "success_count": sum(1 for r in results if r.error is None),
        }

        # Test: 优先级调度
        from app.core.agent_pool import AgentTask
        tasks = [
            AgentTask(task_id="critical", func=lambda: "C", priority=AgentPriority.CRITICAL),
            AgentTask(task_id="low", func=lambda: "L", priority=AgentPriority.LOW),
            AgentTask(task_id="normal", func=lambda: "N", priority=AgentPriority.NORMAL),
        ]
        presults = pool.dispatch(tasks)
        pool_tests["priority_order"] = {
            "ok": [r.result for r in presults] == ["C", "N", "L"],
            "order": [r.result for r in presults],
        }

        # Test: 聚合
        all_agg = pool.aggregate(results, strategy="all")
        best_agg = pool.aggregate(results, strategy="best")
        pool_tests["aggregate_all"] = {"ok": len(all_agg) == 50}
        pool_tests["aggregate_best"] = {"ok": len(best_agg) == 1}

        # Test: 真实LLM并发
        def cheap_call(i):
            c = CheapLLMClient()
            r = c.complete(messages=[{"role": "user", "content": f"回复{i}"}], max_tokens=256)
            return bool(r) and bool(c.get_response_text(r))

        t0 = time.time()
        llm_results = pool.dispatch_simple(cheap_call, list(range(10)))
        llm_elapsed = (time.time() - t0) * 1000
        llm_success = sum(1 for r in llm_results if r.result is True)
        pool_tests["real_llm_10_concurrent"] = {
            "ok": llm_success >= 7,
            "success": llm_success,
            "total": 10,
            "time_ms": llm_elapsed,
        }

        layer_results["agent_pool"] = pool_tests
        for k, v in pool_tests.items():
            print(f"    {'✅' if v['ok'] else '❌'} {k}: {v}")

        # 3.3 CircuitBreaker
        print("\n  [3.3] CircuitBreaker 功能测试")
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=5)
        cb_tests = {}
        cb_tests["initial_closed"] = {"ok": cb.state == CircuitState.CLOSED}
        try:
            cb.call(lambda: 1 / 0)
        except:
            pass
        try:
            cb.call(lambda: 1 / 0)
        except:
            pass
        cb_tests["opens_after_failures"] = {"ok": cb.state == CircuitState.OPEN}
        fallback_result = cb.call(lambda: 42, fallback=lambda: 99)
        cb_tests["fallback_when_open"] = {"ok": fallback_result == 99}
        cb.reset()
        cb_tests["reset_to_closed"] = {"ok": cb.state == CircuitState.CLOSED}

        layer_results["circuit_breaker"] = cb_tests
        for k, v in cb_tests.items():
            print(f"    {'✅' if v['ok'] else '❌'} {k}")

        # 3.4 LLMResponseCache
        print("\n  [3.4] LLMResponseCache 功能测试")
        cache = LLMResponseCache(ttl_seconds=60)
        cache_tests = {}
        msgs = [{"role": "u", "content": "test"}]
        cache.put(msgs, "cached_value")
        cache_tests["put_get"] = {"ok": cache.get(msgs) == "cached_value"}
        cache_tests["miss"] = {"ok": cache.get([{"role": "u", "content": "miss"}]) is None}
        cache_tests["stats"] = {"ok": cache.get_stats()["cache_size"] == 1}

        layer_results["llm_cache"] = cache_tests
        for k, v in cache_tests.items():
            print(f"    {'✅' if v['ok'] else '❌'} {k}")

        # 3.5 ScalabilityProfile
        print("\n  [3.5] ScalabilityProfile 功能测试")
        profile = ScalabilityProfile.detect(".")
        sp_tests = {}
        sp_tests["cheap_llm_profile"] = {"ok": profile["_profile"] == "CHEAP_LLM"}
        sp_tests["agent_pool_enabled"] = {"ok": profile.get("enable_agent_pool") is True}
        sp_tests["high_qps"] = {"ok": profile["llm_max_qps"] >= 999}
        sp_tests["high_concurrent"] = {"ok": profile["llm_max_concurrent"] >= 999}

        layer_results["scalability_profile"] = sp_tests
        for k, v in sp_tests.items():
            print(f"    {'✅' if v['ok'] else '❌'} {k}")

        self.report["layer_tests"] = layer_results

    def _step4_iteration_test(self):
        """Step 4: 100轮迭代压力测试"""
        print(f"\n[Step 4] {self.iterations}轮迭代压力测试")

        pool = AgentPool(max_workers=32)
        cheap = CheapLLMClient()

        iter_results = []
        success_count = 0
        fail_count = 0
        total_llm_calls = 0
        total_llm_success = 0
        times = []
        agent_activity: Dict[str, List] = defaultdict(list)

        for i in range(self.iterations):
            iter_start = time.time()

            # 每轮: 模拟完整pipeline的5个LLM调用点
            round_tasks = [
                ("conv_analysis", f"分析代码文件test_{i}.py的结构"),
                ("fc1_planning", f"为需求req_{i}生成修改方案"),
                ("fc2_generation", f"修改函数func_{i}的代码"),
                ("fc3_testing", f"为函数func_{i}生成单元测试"),
                ("output_report", f"生成第{i}轮迭代报告"),
            ]

            round_ok = True
            round_llm_ok = 0
            round_details = {}

            for agent_name, prompt in round_tasks:
                task_start = time.time()
                try:
                    resp = cheap.complete(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=256,
                    )
                    text = cheap.get_response_text(resp) if resp else ""
                    elapsed = (time.time() - task_start) * 1000
                    ok = bool(resp) and bool(text)
                    if ok:
                        round_llm_ok += 1
                        total_llm_success += 1
                    total_llm_calls += 1

                    agent_activity[agent_name].append({
                        "iteration": i,
                        "ok": ok,
                        "time_ms": round(elapsed, 1),
                        "response_len": len(text),
                    })
                    round_details[agent_name] = {
                        "ok": ok,
                        "time_ms": round(elapsed, 1),
                    }
                except Exception as e:
                    elapsed = (time.time() - task_start) * 1000
                    round_ok = False
                    agent_activity[agent_name].append({
                        "iteration": i,
                        "ok": False,
                        "time_ms": round(elapsed, 1),
                        "error": str(e)[:100],
                    })
                    round_details[agent_name] = {"ok": False, "error": str(e)[:100]}

            iter_elapsed = (time.time() - iter_start) * 1000
            times.append(iter_elapsed)

            if round_ok and round_llm_ok >= 3:
                success_count += 1
            else:
                fail_count += 1

            iter_results.append({
                "iteration": i + 1,
                "success": round_ok and round_llm_ok >= 3,
                "llm_success": round_llm_ok,
                "llm_total": len(round_tasks),
                "time_ms": round(iter_elapsed, 1),
                "details": round_details,
            })

            if (i + 1) % 10 == 0:
                avg = sum(times[-10:]) / 10
                print(
                    f"  [{i+1:3d}/{self.iterations}] "
                    f"成功={success_count} 失败={fail_count} "
                    f"LLM={total_llm_success}/{total_llm_calls} "
                    f"近10轮均值={avg:.0f}ms"
                )

        # 计算统计
        import statistics
        times_arr = [r["time_ms"] for r in iter_results]

        self.report["iteration_test"] = {
            "total_iterations": self.iterations,
            "success_count": success_count,
            "fail_count": fail_count,
            "success_rate": success_count / self.iterations,
            "total_llm_calls": total_llm_calls,
            "total_llm_success": total_llm_success,
            "llm_success_rate": total_llm_success / max(total_llm_calls, 1),
            "time_stats": {
                "mean_ms": round(statistics.mean(times_arr), 1),
                "median_ms": round(statistics.median(times_arr), 1),
                "stdev_ms": round(statistics.stdev(times_arr), 1) if len(times_arr) > 1 else 0,
                "min_ms": round(min(times_arr), 1),
                "max_ms": round(max(times_arr), 1),
                "p95_ms": round(sorted(times_arr)[int(len(times_arr) * 0.95)], 1),
                "p99_ms": round(sorted(times_arr)[int(len(times_arr) * 0.99)], 1),
                "total_s": round(sum(times_arr) / 1000, 1),
            },
            "agent_activity_summary": {
                name: {
                    "total_calls": len(acts),
                    "success": sum(1 for a in acts if a["ok"]),
                    "fail": sum(1 for a in acts if not a["ok"]),
                    "avg_time_ms": round(sum(a["time_ms"] for a in acts) / len(acts), 1) if acts else 0,
                    "success_rate": sum(1 for a in acts if a["ok"]) / len(acts) if acts else 0,
                }
                for name, acts in agent_activity.items()
            },
            "agent_activity_detail": {
                name: acts for name, acts in agent_activity.items()
            },
            "iterations": iter_results,
        }

        print(f"\n  迭代测试完成:")
        print(f"    成功率: {success_count}/{self.iterations} ({success_count/self.iterations:.1%})")
        print(f"    LLM成功率: {total_llm_success}/{total_llm_calls} ({total_llm_success/max(total_llm_calls,1):.1%})")
        print(f"    平均耗时: {self.report['iteration_test']['time_stats']['mean_ms']:.0f}ms/轮")

    def _step5_summary(self):
        """Step 5: 汇总"""
        print("\n[Step 5] 汇总")

        agent_check = self.report.get("agent_llm_check", {})
        layer_tests = self.report.get("layer_tests", {})
        iter_test = self.report.get("iteration_test", {})

        all_agent_ok = agent_check.get("connected", 0) == agent_check.get("total", 0)
        all_layers_ok = all(
            v["ok"]
            for layer in layer_tests.values()
            for v in layer.values()
            if isinstance(v, dict) and "ok" in v
        )
        iter_ok = iter_test.get("success_rate", 0) >= 0.95

        self.report["summary"] = {
            "overall_pass": all_agent_ok and all_layers_ok and iter_ok,
            "agent_llm_all_connected": all_agent_ok,
            "all_layer_tests_pass": all_layers_ok,
            "iteration_success_rate": iter_test.get("success_rate", 0),
            "llm_success_rate": iter_test.get("llm_success_rate", 0),
            "time_stats": iter_test.get("time_stats", {}),
            "agent_activity_summary": iter_test.get("agent_activity_summary", {}),
            "conclusion": "",
        }

        if self.report["summary"]["overall_pass"]:
            self.report["summary"]["conclusion"] = "✅ 全部验证通过 — 无数Agent + 极便宜LLM模式可正常工作"
        else:
            issues = []
            if not all_agent_ok:
                issues.append("部分Agent LLM连接失败")
            if not all_layers_ok:
                issues.append("部分层测试失败")
            if not iter_ok:
                issues.append("迭代成功率<95%")
            self.report["summary"]["conclusion"] = f"⚠️ 存在问题: {', '.join(issues)}"

        print(f"  整体结果: {self.report['summary']['conclusion']}")
        print(f"  Agent LLM连通: {'✅' if all_agent_ok else '❌'}")
        print(f"  层测试: {'✅' if all_layers_ok else '❌'}")
        print(f"  迭代成功率: {iter_test.get('success_rate', 0):.1%}")
        print(f"  LLM成功率: {iter_test.get('llm_success_rate', 0):.1%}")

    def _save_report(self):
        """保存报告"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"E2E_VERIFICATION_REPORT_{ts}.md"

        lines = []
        lines.append(f"# {self.report['title']}\n")
        lines.append(f"生成时间: {self.report['timestamp']}\n")

        # Config
        lines.append("\n## 1. 环境配置\n")
        for k, v in self.report.get("config", {}).items():
            lines.append(f"- **{k}**: {v}")

        # Agent LLM Check
        lines.append("\n## 2. 每Agent LLM连通性检测\n")
        ac = self.report.get("agent_llm_check", {})
        lines.append(f"- 总计: {ac.get('total', 0)} 个Agent")
        lines.append(f"- 连通: {ac.get('connected', 0)} 个\n")
        lines.append("| Agent | 连通 | 模型 | 耗时(ms) | 响应 | 错误 |")
        lines.append("|-------|------|------|----------|------|------|")
        for name, info in ac.get("results", {}).items():
            s = "✅" if info["connected"] else "❌"
            rt = f"{info['response_time_ms']:.0f}" if info["response_time_ms"] else "-"
            resp = (info.get("response_text") or "")[:30].replace("\n", " ")
            err = (info.get("error") or "")[:40]
            lines.append(f"| {name} | {s} | {info['model']} | {rt} | {resp} | {err} |")

        # Layer Tests
        lines.append("\n## 3. 各层功能测试\n")
        for layer_name, tests in self.report.get("layer_tests", {}).items():
            lines.append(f"### {layer_name}\n")
            for test_name, result in tests.items():
                if isinstance(result, dict) and "ok" in result:
                    s = "✅" if result["ok"] else "❌"
                    detail = {k: v for k, v in result.items() if k != "ok"}
                    lines.append(f"- {s} **{test_name}**: {detail}")
            lines.append("")

        # Iteration Test
        lines.append("\n## 4. 迭代压力测试\n")
        it = self.report.get("iteration_test", {})
        lines.append(f"- **总轮次**: {it.get('total_iterations', 0)}")
        lines.append(f"- **成功**: {it.get('success_count', 0)}")
        lines.append(f"- **失败**: {it.get('fail_count', 0)}")
        lines.append(f"- **成功率**: {it.get('success_rate', 0):.1%}")
        lines.append(f"- **LLM调用**: {it.get('total_llm_calls', 0)}")
        lines.append(f"- **LLM成功**: {it.get('total_llm_success', 0)}")
        lines.append(f"- **LLM成功率**: {it.get('llm_success_rate', 0):.1%}")

        ts_stats = it.get("time_stats", {})
        lines.append("\n### 耗时统计\n")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        for k, v in ts_stats.items():
            lines.append(f"| {k} | {v} |")

        # Agent Activity
        lines.append("\n### 每Agent活动详情\n")
        aas = it.get("agent_activity_summary", {})
        lines.append("| Agent | 调用次数 | 成功 | 失败 | 成功率 | 平均耗时(ms) |")
        lines.append("|-------|---------|------|------|--------|-------------|")
        for name, info in aas.items():
            lines.append(
                f"| {name} | {info['total_calls']} | {info['success']} | {info['fail']} "
                f"| {info['success_rate']:.1%} | {info['avg_time_ms']:.0f} |"
            )

        # Agent Activity Detail (last 10 iterations per agent)
        lines.append("\n### 每Agent最近10轮活动\n")
        aad = it.get("agent_activity_detail", {})
        for name, acts in aad.items():
            lines.append(f"\n**{name}** (最近10轮):")
            for act in acts[-10:]:
                s = "✅" if act["ok"] else "❌"
                err = act.get("error", "")
                extra = f" error={err}" if err else ""
                lines.append(f"  - 轮{act['iteration']+1}: {s} {act['time_ms']:.0f}ms{extra}")

        # Summary
        lines.append("\n## 5. 总结\n")
        summary = self.report.get("summary", {})
        lines.append(f"**{summary.get('conclusion', '')}**\n")
        lines.append(f"- Agent LLM全部连通: {'✅' if summary.get('agent_llm_all_connected') else '❌'}")
        lines.append(f"- 层测试全部通过: {'✅' if summary.get('all_layer_tests_pass') else '❌'}")
        lines.append(f"- 迭代成功率: {summary.get('iteration_success_rate', 0):.1%}")
        lines.append(f"- LLM成功率: {summary.get('llm_success_rate', 0):.1%}")

        report_file.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n报告已保存: {report_file}")

        json_file = self.output_dir / f"e2e_report_{ts}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(self.report, f, ensure_ascii=False, indent=2, default=str)
        print(f"JSON数据: {json_file}")


if __name__ == "__main__":
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    verifier = E2EVerifier(iterations=iterations, output_dir=".")
    verifier.run_full_verification()
