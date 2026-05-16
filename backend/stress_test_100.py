"""
100轮迭代压力测试 - 验证全流程稳定性、可靠性、协作能力、通用性
策略: 90轮fallback模式(快速压力测试pipeline机制) + 10轮LLM模式(验证真实LLM集成)
"""
import gc
import json
import os
import shutil
import tempfile
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("ANTHROPIC_AUTH_TOKEN", "sk-sp-EYc8Ao3Eohynfn43HMqttD3zYfcE9P1x")
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://aigw-gzgy2.cucloud.cn:8443")

from app.core.llm_client import get_llm_client, LLMClient
from app.core.logging import logger as _logger
from app.services.pipeline.neural_pipeline import NeuralNetworkPipeline
from app.services.backward.service import BackwardPropagationService

DIVERSE_TASKS = [
    ("为所有函数添加类型注解", "python"),
    ("添加异常处理和日志记录", "python"),
    ("重构代码提高可读性", "python"),
    ("添加输入验证", "python"),
    ("优化性能瓶颈", "python"),
    ("添加单元测试覆盖", "python"),
    ("修复安全漏洞", "python"),
    ("实现缓存机制", "python"),
    ("添加配置管理", "python"),
    ("改进错误提示信息", "python"),
]

CODE_TEMPLATES = {
    "python": '''
from typing import Optional

def process_data(data: dict) -> dict:
    result = {}
    for key, value in data.items():
        result[key] = str(value).upper()
    return result

def validate_input(value: str) -> bool:
    return len(value) > 0

class DataHandler:
    def __init__(self, source: str):
        self.source = source
        self.data = {}

    def load(self) -> bool:
        return True

    def transform(self, func) -> dict:
        return {k: func(v) for k, v in self.data.items()}

    def save(self, path: str) -> bool:
        return True
''',
}


class StressTestMetrics:
    def __init__(self):
        self.total_iterations = 0
        self.success_count = 0
        self.fail_count = 0
        self.llm_iterations = 0
        self.fallback_iterations = 0
        self.latencies: List[float] = []
        self.layer_latencies: Dict[str, List[float]] = defaultdict(list)
        self.layer_errors: Dict[str, int] = defaultdict(int)
        self.llm_fallbacks: Dict[str, int] = defaultdict(int)
        self.llm_successes: Dict[str, int] = defaultdict(int)
        self.backward_count = 0
        self.backward_errors = 0
        self.data_flow_errors = 0
        self.memory_snapshots: List[int] = []
        self.task_types_used: set = set()
        self.errors: List[Dict] = []
        self.iteration_details: List[Dict] = []

    def record_iteration(self, detail: Dict):
        self.iteration_details.append(detail)
        self.total_iterations += 1
        if detail["success"]:
            self.success_count += 1
        else:
            self.fail_count += 1
        self.latencies.append(detail["latency_ms"])
        if detail.get("llm_mode"):
            self.llm_iterations += 1
        else:
            self.fallback_iterations += 1
        self.task_types_used.add(detail["task_desc"][:20])
        for layer, info in detail.get("layer_info", {}).items():
            self.layer_latencies[layer].append(info.get("latency_ms", 0))
            if info.get("error"):
                self.layer_errors[layer] += 1
            if info.get("llm_fallback"):
                self.llm_fallbacks[layer] += 1
            if info.get("llm_success"):
                self.llm_successes[layer] += 1


def create_test_repo(task_idx: int) -> str:
    tmpdir = tempfile.mkdtemp(prefix=f"stress_{task_idx}_")
    src = Path(tmpdir) / "src"
    src.mkdir()
    code = CODE_TEMPLATES["python"]
    (src / "handler.py").write_text(code, encoding="utf-8")
    (src / "utils.py").write_text(
        "def helper(x): return x * 2\ndef format_output(s): return str(s).strip()\n",
        encoding="utf-8",
    )
    return tmpdir


def run_single_iteration(
    pipeline: NeuralNetworkPipeline,
    idx: int,
    llm_mode: bool,
    metrics: StressTestMetrics,
) -> Dict:
    task_desc, lang = DIVERSE_TASKS[idx % len(DIVERSE_TASKS)]
    task_id = f"stress_{idx:03d}"
    tmpdir = create_test_repo(idx)

    detail = {
        "iteration": idx,
        "task_id": task_id,
        "task_desc": task_desc,
        "llm_mode": llm_mode,
        "success": False,
        "latency_ms": 0,
        "layer_info": {},
    }

    try:
        t0 = time.time()
        result = pipeline.execute_forward_pipeline(
            task_id=task_id,
            user_requirement=task_desc,
            code_repo_path=tmpdir,
        )
        elapsed = (time.time() - t0) * 1000
        detail["latency_ms"] = elapsed

        layers = result.get("layer_outputs", {})

        for layer_name, layer_data in layers.items():
            info = {"latency_ms": 0, "error": False, "llm_fallback": False, "llm_success": False}
            if isinstance(layer_data, dict):
                if "error" in layer_data:
                    info["error"] = True
                mods = layer_data.get("modifications", [])
                tests = layer_data.get("tests", [])
                for m in mods:
                    if m.get("generated_by") == "llm":
                        info["llm_success"] = True
                    elif m.get("generated_by") == "template":
                        info["llm_fallback"] = True
                for t in tests:
                    if t.get("generated_by") == "llm":
                        info["llm_success"] = True
                    elif t.get("generated_by") == "template":
                        info["llm_fallback"] = True
                if layer_data.get("solution", {}).get("overview", ""):
                    analyzed_by = layer_data.get("analyzed_by", "")
                    if analyzed_by == "llm":
                        info["llm_success"] = True
            detail["layer_info"][layer_name] = info

        has_error = any(v.get("error") for v in layers.values() if isinstance(v, dict) and "error" in v)
        if not has_error:
            detail["success"] = True
        else:
            detail["success"] = False
            metrics.data_flow_errors += 1

    except Exception as e:
        detail["latency_ms"] = (time.time() - t0) * 1000 if 't0' in dir() else 0
        detail["error_msg"] = str(e)[:200]
        metrics.errors.append({"iteration": idx, "error": str(e)[:200]})

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    metrics.record_iteration(detail)
    return detail


def run_backward_pass(
    backward_svc: BackwardPropagationService,
    idx: int,
    metrics: StressTestMetrics,
) -> bool:
    try:
        score = 3 + (idx % 8)
        result = backward_svc.process_user_feedback(
            f"stress_{idx:03d}",
            {
                "satisfaction_score": score,
                "comments": f"Feedback for iteration {idx}",
                "feedback_items": [{"layer": "fc2", "feedback": "improve quality"}],
                "iteration_number": idx,
            },
        )
        metrics.backward_count += 1
        return True
    except Exception:
        metrics.backward_errors += 1
        return False


def print_progress(idx: int, total: int, detail: Dict, start_time: float):
    bar_len = 40
    filled = int(bar_len * (idx + 1) / total)
    bar = "#" * filled + "-" * (bar_len - filled)
    elapsed = time.time() - start_time
    eta = elapsed / (idx + 1) * (total - idx - 1) if idx > 0 else 0
    mode = "LLM" if detail.get("llm_mode") else "FB"
    status = "OK" if detail.get("success") else "FAIL"
    lat = detail.get("latency_ms", 0)
    print(
        f"\r  [{bar}] {idx+1}/{total} | {mode} | {status} | {lat:.0f}ms | ETA:{eta:.0f}s",
        end="",
        flush=True,
    )


def print_final_report(metrics: StressTestMetrics, total_time: float):
    print("\n\n" + "=" * 70)
    print("  100轮迭代压力测试报告")
    print("=" * 70)

    # 基础统计
    print(f"\n[1] 基础统计")
    print(f"  总迭代:     {metrics.total_iterations}")
    print(f"  成功:       {metrics.success_count} ({metrics.success_count/metrics.total_iterations*100:.1f}%)")
    print(f"  失败:       {metrics.fail_count} ({metrics.fail_count/metrics.total_iterations*100:.1f}%)")
    print(f"  LLM模式:    {metrics.llm_iterations}")
    print(f"  Fallback:   {metrics.fallback_iterations}")
    print(f"  总耗时:     {total_time:.1f}s")

    # 延迟统计
    if metrics.latencies:
        avg_lat = sum(metrics.latencies) / len(metrics.latencies)
        min_lat = min(metrics.latencies)
        max_lat = max(metrics.latencies)
        p50 = sorted(metrics.latencies)[len(metrics.latencies) // 2]
        p95 = sorted(metrics.latencies)[int(len(metrics.latencies) * 0.95)]
        print(f"\n[2] 延迟统计 (ms)")
        print(f"  Avg: {avg_lat:.0f}  Min: {min_lat:.0f}  Max: {max_lat:.0f}  P50: {p50:.0f}  P95: {p95:.0f}")

    # 各层统计
    print(f"\n[3] 各层统计")
    all_layers = set(metrics.layer_latencies.keys()) | set(metrics.layer_errors.keys()) | set(metrics.llm_fallbacks.keys()) | set(metrics.llm_successes.keys())
    for layer in sorted(all_layers):
        lats = metrics.layer_latencies.get(layer, [])
        avg = sum(lats) / len(lats) if lats else 0
        errs = metrics.layer_errors.get(layer, 0)
        fb = metrics.llm_fallbacks.get(layer, 0)
        llm_ok = metrics.llm_successes.get(layer, 0)
        print(f"  {layer:<30} avg={avg:>8.0f}ms  err={errs}  llm_ok={llm_ok}  fallback={fb}")

    # 反向传播
    print(f"\n[4] 反向传播")
    print(f"  执行次数:   {metrics.backward_count}")
    print(f"  错误次数:   {metrics.backward_errors}")

    # 数据流完整性
    print(f"\n[5] 数据流完整性")
    print(f"  数据流错误: {metrics.data_flow_errors}")

    # 通用性
    print(f"\n[6] 通用性")
    print(f"  任务类型覆盖: {len(metrics.task_types_used)}/{len(DIVERSE_TASKS)}")

    # 稳定性
    if len(metrics.latencies) > 1:
        mean = sum(metrics.latencies) / len(metrics.latencies)
        variance = sum((x - mean) ** 2 for x in metrics.latencies) / len(metrics.latencies)
        std_dev = variance**0.5
        cv = std_dev / mean if mean > 0 else 0
        print(f"\n[7] 稳定性")
        print(f"  延迟标准差: {std_dev:.0f}ms")
        print(f"  变异系数CV: {cv:.2f} ({'稳定' if cv < 0.5 else '波动较大'})")

    # 优化建议
    print(f"\n{'='*70}")
    print(f"  优化建议")
    print(f"{'='*70}")
    suggestions = []

    if metrics.fail_count > 0:
        rate = metrics.fail_count / metrics.total_iterations * 100
        suggestions.append(f"[可靠性] 失败率{rate:.1f}%，建议：增加重试机制、改善错误恢复逻辑")

    total_fb = sum(metrics.llm_fallbacks.values())
    total_llm_ok = sum(metrics.llm_successes.values())
    if total_fb > 0 and total_llm_ok > 0:
        fb_rate = total_fb / (total_fb + total_llm_ok) * 100
        if fb_rate > 30:
            suggestions.append(f"[LLM] LLM降级率{fb_rate:.0f}%偏高，建议：增加API并发/换更稳定模型/增加请求间隔")

    if metrics.latencies:
        p95 = sorted(metrics.latencies)[int(len(metrics.latencies) * 0.95)]
        if p95 > 10000:
            suggestions.append(f"[性能] P95延迟{p95:.0f}ms过高，建议：异步并行化层间调用、缓存LLM结果、减少冗余JSON序列化")

    if metrics.data_flow_errors > 0:
        suggestions.append(f"[数据流] {metrics.data_flow_errors}次数据流错误，建议：添加层间数据schema校验、增加中间结果缓存")

    if metrics.backward_errors > 0:
        suggestions.append(f"[反向传播] {metrics.backward_errors}次错误，建议：TrustManager增加内存fallback、DB连接池优化")

    if len(metrics.task_types_used) < len(DIVERSE_TASKS):
        suggestions.append(f"[通用性] 仅覆盖{len(metrics.task_types_used)}/{len(DIVERSE_TASKS)}任务类型，建议：扩展多语言代码分析(JS/Go/Java)")

    suggestions.append("[协作] 建议：Input→Conv层间传递enriched_requirement、Pooling→FC1传递LLM压缩摘要、FC2修改结果直接写回代码文件")
    suggestions.append("[缓存] 建议：添加LLM响应缓存(相同prompt不重复调用)、添加层间结果缓存(迭代间复用未变层输出)")
    suggestions.append("[并行] 建议：FC2多个文件修改可并行调用LLM、FC3测试生成可并行、卷积层多文件分析可并行")
    suggestions.append("[监控] 建议：添加Prometheus指标(每层延迟/错误率/LLM token用量)、添加迭代收敛曲线可视化")

    for i, s in enumerate(suggestions, 1):
        print(f"  {i}. {s}")


def main():
    TOTAL = 100
    LLM_EVERY = 10

    print("=" * 70)
    print("  100轮迭代压力测试")
    print(f"  策略: 每{LLM_EVERY}轮启用LLM, 其余fallback模式")
    print("=" * 70)

    metrics = StressTestMetrics()
    pipeline = NeuralNetworkPipeline()
    backward_svc = BackwardPropagationService()

    has_llm_key = bool(os.environ.get("ANTHROPIC_AUTH_TOKEN", ""))
    if not has_llm_key:
        from dotenv import load_dotenv
        load_dotenv()
        has_llm_key = bool(os.environ.get("ANTHROPIC_AUTH_TOKEN", ""))

    print(f"\n  LLM API Key: {'已配置' if has_llm_key else '未配置(仅fallback)'}")

    start_time = time.time()

    for idx in range(TOTAL):
        use_llm = (idx % LLM_EVERY == 0) and has_llm_key

        if use_llm:
            client = get_llm_client()
            client._available = None
        else:
            client = get_llm_client()
            client._available = False

        detail = run_single_iteration(pipeline, idx, use_llm, metrics)
        print_progress(idx, TOTAL, detail, start_time)

        if idx % 5 == 4:
            run_backward_pass(backward_svc, idx, metrics)

        if idx % 20 == 19:
            gc.collect()

    client = get_llm_client()
    client._available = None

    total_time = time.time() - start_time
    print_final_report(metrics, total_time)


if __name__ == "__main__":
    main()
