"""
完整复杂任务验证 - 逐Agent详细活动报告
逐层调用每个Agent，记录输入/输出/耗时/LLM状态/降级情况
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

os.environ["MAX_CONCURRENT_MODS"] = "2"
os.environ["MAX_CONCURRENT_TESTS"] = "2"


def save_report():
    output_dir = Path("task_output") / "comprehensive_verify"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "agent_detail_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def fmt_dict(d: Any, max_len: int = 500) -> str:
    if d is None:
        return "None"
    if isinstance(d, dict):
        items = []
        for k, v in d.items():
            s = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v
            if len(s) > max_len:
                s = s[:max_len] + "..."
            items.append(f"  {k}: {s}")
        return "{\n" + "\n".join(items) + "\n}"
    s = str(d)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def print_header(title: str):
    print(f"\n{'#'*80}")
    print(f"# {title}")
    print(f"{'#'*80}")


def print_agent_block(
    layer: str, agent: str, status: str, elapsed_ms: float,
    llm_mode: str, input_desc: str, output_desc: str,
    details: Dict[str, Any] = None
):
    print(f"\n{'─'*80}")
    print(f"  层级: {layer}")
    print(f"  Agent: {agent}")
    print(f"  状态: {status}")
    print(f"  耗时: {elapsed_ms:.1f}ms ({elapsed_ms/1000:.2f}s)")
    print(f"  LLM模式: {llm_mode}")
    print(f"  输入摘要: {input_desc}")
    print(f"  输出摘要: {output_desc}")
    if details:
        for k, v in details.items():
            print(f"  {k}: {v}")
    print(f"{'─'*80}")


# =====================================================================
TASK_ID = f"full_agent_verify_{int(time.time())}"
CODE_REPO = "app/core"
USER_REQUIREMENT = "Add comprehensive error handling and input validation to the config module, ensuring all settings are validated on startup"

report = {
    "task_id": TASK_ID,
    "user_requirement": USER_REQUIREMENT,
    "code_repo": CODE_REPO,
    "timestamp": datetime.now().isoformat(),
    "agents": [],
    "backward": None,
    "iteration": None,
    "summary": None,
}

print_header(f"Neural Agent System - 逐Agent详细验证")
print(f"  任务ID: {TASK_ID}")
print(f"  代码路径: {CODE_REPO}")
print(f"  用户需求: {USER_REQUIREMENT}")

# =====================================================================
# L0: Input Layer
# =====================================================================
print_header("L0: Input Layer (输入层)")

from app.services.input_layer.service import input_layer_service
from app.core.llm_client import get_llm_client

llm = get_llm_client()
t0 = time.time()

# 需求丰富
original_req = USER_REQUIREMENT
enriched_req = input_layer_service.enrich_requirement(USER_REQUIREMENT)
input_elapsed = (time.time() - t0) * 1000

llm_used_input = enriched_req != original_req
input_mode = "LLM增强" if llm_used_input else "原文透传(fallback)"

print_agent_block(
    layer="L0 Input", agent="InputLayerService", status="✅ SUCCESS",
    elapsed_ms=input_elapsed, llm_mode=input_mode,
    input_desc=f"用户需求({len(original_req)}字符): {original_req[:100]}...",
    output_desc=f"丰富后需求({len(enriched_req)}字符): {enriched_req[:150]}...",
    details={
        "需求扩展比": f"{len(enriched_req)/len(original_req):.1f}x",
        "LLM available": str(llm.is_available),
    }
)

report["agents"].append({
    "layer": "L0 Input", "agent": "InputLayerService", "status": "success",
    "elapsed_ms": input_elapsed, "llm_mode": input_mode,
    "input_len": len(original_req), "output_len": len(enriched_req),
})
save_report()

# =====================================================================
# L1: Convolution Layer
# =====================================================================
print_header("L1: Convolution Layer (卷积层)")

from app.services.convolution.service import get_convolution_service

conv_service = get_convolution_service()
t1 = time.time()
try:
    conv_output = conv_service.process_task(TASK_ID, CODE_REPO)
    conv_elapsed = (time.time() - t1) * 1000
    conv_error = None
except Exception as e:
    conv_output = {"error": str(e), "task_id": TASK_ID}
    conv_elapsed = (time.time() - t1) * 1000
    conv_error = str(e)

analyzed_files = conv_output.get("analyzed_files", [])
failed_files = conv_output.get("failed_files", [])
conv_summary = conv_output.get("summary", {})
conv_mode = "LLM+Tree-sitter" if llm.is_available else "Tree-sitter仅(fallback)"

print_agent_block(
    layer="L1 Conv", agent="ConvolutionService", status="✅ SUCCESS" if not conv_error else "❌ FAIL",
    elapsed_ms=conv_elapsed, llm_mode=conv_mode,
    input_desc=f"代码路径: {CODE_REPO}",
    output_desc=f"分析{len(analyzed_files)}个文件, {len(failed_files)}个失败",
    details={
        "成功文件数": len(analyzed_files),
        "失败文件数": len(failed_files),
        "摘要": fmt_dict(conv_summary, 200),
    }
)

# 打印每个文件分析详情
for i, f in enumerate(analyzed_files[:5]):
    fname = f.get("file_name", f.get("path", "unknown"))
    lang = f.get("language", "unknown")
    funcs = f.get("functions", [])
    classes = f.get("classes", [])
    print(f"    [{i+1}] {fname} ({lang}): {len(funcs)}函数, {len(classes)}类")
if len(analyzed_files) > 5:
    print(f"    ... 还有{len(analyzed_files)-5}个文件")

report["agents"].append({
    "layer": "L1 Conv", "agent": "ConvolutionService",
    "status": "success" if not conv_error else "fail",
    "elapsed_ms": conv_elapsed, "llm_mode": conv_mode,
    "files_analyzed": len(analyzed_files), "files_failed": len(failed_files),
})
save_report()

# =====================================================================
# L2: Pooling Layer
# =====================================================================
print_header("L2: Pooling Layer (池化层)")

from app.services.pooling.service import get_pooling_service

pool_service = get_pooling_service()
t2 = time.time()
try:
    pool_output = pool_service.process_task(TASK_ID, conv_output, enriched_req)
    pool_elapsed = (time.time() - t2) * 1000
    pool_error = None
except Exception as e:
    pool_output = {"error": str(e), "task_id": TASK_ID}
    pool_elapsed = (time.time() - t2) * 1000
    pool_error = str(e)

compressed = pool_output.get("compressed_features", [])
global_features = pool_output.get("global_features", {})
total_processed = pool_output.get("total_files_processed", 0)
pool_mode = "LLM语义压缩" if llm.is_available else "关键词匹配(fallback)"

print_agent_block(
    layer="L2 Pool", agent="PoolingService", status="✅ SUCCESS" if not pool_error else "❌ FAIL",
    elapsed_ms=pool_elapsed, llm_mode=pool_mode,
    input_desc=f"{len(analyzed_files)}个分析文件",
    output_desc=f"压缩为{len(compressed)}个特征, 处理{total_processed}个文件",
    details={
        "压缩特征数": len(compressed),
        "全局特征": fmt_dict(global_features, 200),
    }
)

for i, c in enumerate(compressed[:3]):
    name = c.get("name", c.get("file_name", "unknown"))
    relevance = c.get("relevance_score", c.get("importance", "N/A"))
    print(f"    [{i+1}] {name}: relevance={relevance}")

report["agents"].append({
    "layer": "L2 Pool", "agent": "PoolingService",
    "status": "success" if not pool_error else "fail",
    "elapsed_ms": pool_elapsed, "llm_mode": pool_mode,
    "compressed_features": len(compressed), "files_processed": total_processed,
})
save_report()

# =====================================================================
# L3: FC1 Global Understanding
# =====================================================================
print_header("L3: FC1 Global Understanding (全局理解层)")

from app.services.fullconnect import get_global_understanding_service

fc1_service = get_global_understanding_service()
t3 = time.time()
try:
    fc1_output = fc1_service.process_task(TASK_ID, pool_output, enriched_req)
    fc1_elapsed = (time.time() - t3) * 1000
    fc1_error = None
except Exception as e:
    fc1_output = {"error": str(e), "task_id": TASK_ID}
    fc1_elapsed = (time.time() - t3) * 1000
    fc1_error = str(e)

solution = fc1_output.get("solution", {})
mod_list = solution.get("modification_list", [])
fc1_mode = "LLM方案生成" if llm.is_available else "规则引擎(fallback)"

print_agent_block(
    layer="L3 FC1", agent="SolutionPlanner", status="✅ SUCCESS" if not fc1_error else "❌ FAIL",
    elapsed_ms=fc1_elapsed, llm_mode=fc1_mode,
    input_desc=f"压缩特征{len(compressed)}个 + 用户需求",
    output_desc=f"方案含{len(mod_list)}项修改",
    details={
        "修改项数": len(mod_list),
        "方案摘要": fmt_dict(solution.get("summary", {}), 200),
    }
)

for i, m in enumerate(mod_list[:5]):
    target = m.get("target", "unknown")
    action = m.get("action", "unknown")
    priority = m.get("priority", "N/A")
    gen_by = m.get("generated_by", "N/A")
    print(f"    [{i+1}] target={target}, action={action}, priority={priority}, by={gen_by}")

report["agents"].append({
    "layer": "L3 FC1", "agent": "SolutionPlanner",
    "status": "success" if not fc1_error else "fail",
    "elapsed_ms": fc1_elapsed, "llm_mode": fc1_mode,
    "modifications": len(mod_list),
})
save_report()

# =====================================================================
# L4: FC2 Code Generation
# =====================================================================
print_header("L4: FC2 Code Generation (代码生成层)")

from app.services.fullconnect import get_code_generation_service

fc2_service = get_code_generation_service()
t4 = time.time()
try:
    fc2_output = fc2_service.process_task(TASK_ID, fc1_output, CODE_REPO)
    fc2_elapsed = (time.time() - t4) * 1000
    fc2_error = None
except Exception as e:
    fc2_output = {"error": str(e), "task_id": TASK_ID}
    fc2_elapsed = (time.time() - t4) * 1000
    fc2_error = str(e)

fc2_summary = fc2_output.get("summary", {})
successful_mods = fc2_summary.get("successful", 0)
failed_mods = fc2_summary.get("failed", 0)
applied_mods = fc2_output.get("modifications", [])
fc2_mode = "LLM代码生成" if llm.is_available else "模板标记(fallback)"

print_agent_block(
    layer="L4 FC2", agent="CodeModifier", status="✅ SUCCESS" if not fc2_error else "❌ FAIL",
    elapsed_ms=fc2_elapsed, llm_mode=fc2_mode,
    input_desc=f"{len(mod_list)}项修改方案 + 代码库",
    output_desc=f"成功{successful_mods}项, 失败{failed_mods}项",
    details={
        "成功修改": successful_mods,
        "失败修改": failed_mods,
        "总计": len(applied_mods),
    }
)

for i, m in enumerate(applied_mods[:5]):
    target = m.get("target", "unknown")
    gen_by = m.get("generated_by", "N/A")
    manual = m.get("requires_manual_review", False)
    diff_preview = m.get("diff", "")[:80]
    print(f"    [{i+1}] target={target}, by={gen_by}, manual_review={manual}")
    print(f"        diff: {diff_preview}...")

report["agents"].append({
    "layer": "L4 FC2", "agent": "CodeModifier",
    "status": "success" if not fc2_error else "fail",
    "elapsed_ms": fc2_elapsed, "llm_mode": fc2_mode,
    "successful": successful_mods, "failed": failed_mods,
})
save_report()

# =====================================================================
# L5: FC3 Test Generation
# =====================================================================
print_header("L5: FC3 Test Generation (测试生成层)")

from app.services.fullconnect import get_test_generation_service

fc3_service = get_test_generation_service()
t5 = time.time()
try:
    fc3_output = fc3_service.process_task(TASK_ID, fc2_output)
    fc3_elapsed = (time.time() - t5) * 1000
    fc3_error = None
except Exception as e:
    fc3_output = {"error": str(e), "task_id": TASK_ID}
    fc3_elapsed = (time.time() - t5) * 1000
    fc3_error = str(e)

fc3_summary = fc3_output.get("summary", {})
total_tests = fc3_summary.get("total_tests", 0)
unit_tests = fc3_summary.get("unit_tests", 0)
integration_tests = fc3_summary.get("integration_tests", 0)
coverage = fc3_summary.get("estimated_coverage", 0)
fc3_mode = "LLM测试生成" if llm.is_available else "模板测试(fallback)"

print_agent_block(
    layer="L5 FC3", agent="TestCaseGenerator", status="✅ SUCCESS" if not fc3_error else "❌ FAIL",
    elapsed_ms=fc3_elapsed, llm_mode=fc3_mode,
    input_desc=f"FC2输出({successful_mods}项修改)",
    output_desc=f"生成{total_tests}个测试: {unit_tests}单元+{integration_tests}集成",
    details={
        "总测试数": total_tests,
        "单元测试": unit_tests,
        "集成测试": integration_tests,
        "估计覆盖率": f"{coverage*100:.0f}%" if coverage else "N/A",
    }
)

test_results = fc3_output.get("test_results", [])
for i, tr in enumerate(test_results[:3]):
    target = tr.get("target", "unknown")
    ttype = tr.get("test_type", "unknown")
    gen_by = tr.get("generated_by", "N/A")
    code_len = len(tr.get("test_code", ""))
    print(f"    [{i+1}] target={target}, type={ttype}, by={gen_by}, code={code_len}chars")

report["agents"].append({
    "layer": "L5 FC3", "agent": "TestCaseGenerator",
    "status": "success" if not fc3_error else "fail",
    "elapsed_ms": fc3_elapsed, "llm_mode": fc3_mode,
    "total_tests": total_tests, "coverage": coverage,
})
save_report()

# =====================================================================
# L6: Output Layer
# =====================================================================
print_header("L6: Output Layer (输出层)")

from app.services.output.service import get_output_service

output_service = get_output_service()
t6 = time.time()
total_exec_ms = input_elapsed + conv_elapsed + pool_elapsed + fc1_elapsed + fc2_elapsed + fc3_elapsed
try:
    output_result = output_service.process_task(
        TASK_ID, enriched_req, fc1_output, fc2_output, fc3_output, total_exec_ms
    )
    output_elapsed = (time.time() - t6) * 1000
    output_error = None
except Exception as e:
    output_result = {"error": str(e), "task_id": TASK_ID}
    output_elapsed = (time.time() - t6) * 1000
    output_error = str(e)

doc_path = output_result.get("document_path", "unknown")
stats = output_result.get("statistics", {})
output_mode = "LLM文档生成" if llm.is_available else "模板拼接(fallback)"

print_agent_block(
    layer="L6 Output", agent="OutputService", status="✅ SUCCESS" if not output_error else "❌ FAIL",
    elapsed_ms=output_elapsed, llm_mode=output_mode,
    input_desc="FC1+FC2+FC3输出",
    output_desc=f"文档: {doc_path}",
    details={
        "文档路径": doc_path,
        "统计": fmt_dict(stats, 200),
    }
)

# 打印文档内容预览
if doc_path and Path(doc_path).exists():
    doc_content = Path(doc_path).read_text(encoding="utf-8", errors="replace")
    print(f"\n  📄 文档内容预览 (前500字符):")
    print(f"  {'─'*60}")
    for line in doc_content[:500].split("\n"):
        print(f"  {line}")
    print(f"  {'─'*60}")
    print(f"  文档总长: {len(doc_content)}字符")

report["agents"].append({
    "layer": "L6 Output", "agent": "OutputService",
    "status": "success" if not output_error else "fail",
    "elapsed_ms": output_elapsed, "llm_mode": output_mode,
    "document_path": doc_path,
})
save_report()

# =====================================================================
# BP: Backward Propagation
# =====================================================================
print_header("BP: Backward Propagation (反向传播)")

from app.agents.trust.backward import BackwardPropagation, RewardCalculator

bp = BackwardPropagation()
rc = RewardCalculator()

user_feedback = {
    "satisfaction_score": 4,
    "feedback_items": [
        {"type": "positive", "description": "Error handling added correctly"},
        {"type": "negative", "description": "Some edge cases not covered"},
    ],
}

reward = rc.calculate_reward(user_feedback)
print(f"  奖励值: {reward:.3f}")
print(f"  (满意度4分→base_reward=0.5, 1个positive+0.1, 1个negative-0.1 → total={reward:.3f})")

layer_agents = {
    "output": ["output_1"],
    "test_generation": ["fc3_1"],
    "code_generation": ["fc2_1"],
    "global_understanding": ["fc1_1"],
    "pooling": ["pool_1"],
    "convolution": ["conv_1"],
}

t_bp = time.time()
try:
    bp_result = bp.propagate_feedback(
        task_id=TASK_ID,
        user_feedback=user_feedback,
        layer_agents=layer_agents,
        current_iteration=1
    )
    bp_elapsed = (time.time() - t_bp) * 1000
    bp_error = None
except Exception as e:
    bp_result = {}
    bp_elapsed = (time.time() - t_bp) * 1000
    bp_error = str(e)

print_agent_block(
    layer="BP Backward", agent="BackwardPropagation", status="✅ SUCCESS" if not bp_error else "❌ FAIL",
    elapsed_ms=bp_elapsed, llm_mode="数学公式(信任度更新)",
    input_desc=f"反馈: satisfaction=4, 1positive+1negative → reward={reward:.3f}",
    output_desc=f"更新{len(bp_result)}个Agent权重",
)

for agent_id, weights in bp_result.items():
    weight_str = ", ".join(f"{k}={v:.3f}" for k, v in weights.items())
    print(f"    {agent_id}: {weight_str}")

report["backward"] = {
    "reward": reward,
    "elapsed_ms": bp_elapsed,
    "updated_weights": {k: {kk: float(vv) for kk, vv in v.items()} for k, v in bp_result.items()},
}

# =====================================================================
# 迭代循环验证
# =====================================================================
print_header("Iteration: 迭代循环验证")

from app.services.pipeline.iteration_manager import IterationManager

mgr = IterationManager()
session = mgr.create_session(
    task_id=TASK_ID,
    user_requirement=enriched_req,
    code_repo_path=CODE_REPO,
    max_iteration=3
)

iteration_log = []

# Round 1
s1 = session.start_iteration()
t_fwd1 = time.time()
session.complete_forward(s1, {"status": "completed"}, start_time=t_fwd1)
session.receive_feedback(s1, {"satisfaction_score": 3.0, "stop_iteration": False})
stop1 = session.should_stop({"satisfaction_score": 3.0, "stop_iteration": False})
iteration_log.append({
    "round": 1, "forward_ms": s1.forward_time_ms,
    "feedback_score": 3.0, "should_stop": stop1, "action": "继续迭代"
})
print(f"  第1轮: forward={s1.forward_time_ms:.1f}ms, satisfaction=3.0 → {'停止' if stop1 else '继续'}")

if not stop1:
    session.mark_iterating()
    s2 = session.start_iteration()
    t_fwd2 = time.time()
    session.complete_forward(s2, {"status": "completed"}, start_time=t_fwd2)
    session.receive_feedback(s2, {"satisfaction_score": 5.0, "stop_iteration": False})
    stop2 = session.should_stop({"satisfaction_score": 5.0, "stop_iteration": False})
    iteration_log.append({
        "round": 2, "forward_ms": s2.forward_time_ms,
        "feedback_score": 5.0, "should_stop": stop2, "action": "满意度满分→停止"
    })
    print(f"  第2轮: forward={s2.forward_time_ms:.1f}ms, satisfaction=5.0 → {'停止' if stop2 else '继续'}")
    session.mark_completed()

print(f"\n  最终状态: iteration={session.current_iteration}, status={session.status}")
print(f"  迭代历史:")
for il in iteration_log:
    print(f"    第{il['round']}轮: forward={il['forward_ms']:.1f}ms, score={il['feedback_score']}, {il['action']}")

mgr.save_iteration_result(TASK_ID)

report["iteration"] = {
    "total_rounds": session.current_iteration,
    "final_status": session.status,
    "history": iteration_log,
}

# =====================================================================
# 总报告
# =====================================================================
print_header("验证总报告")

total_elapsed = input_elapsed + conv_elapsed + pool_elapsed + fc1_elapsed + fc2_elapsed + fc3_elapsed + output_elapsed + bp_elapsed
all_success = all(a["status"] == "success" for a in report["agents"])

print(f"\n  任务ID: {TASK_ID}")
print(f"  总耗时: {total_elapsed:.0f}ms ({total_elapsed/1000:.1f}s)")
print(f"  所有Agent成功: {'✅ 是' if all_success else '❌ 否'}")
print(f"\n  各Agent耗时分布:")

for a in report["agents"]:
    pct = a["elapsed_ms"] / total_elapsed * 100 if total_elapsed > 0 else 0
    bar = "█" * int(pct / 2)
    print(f"    {a['layer']:12s} │ {a['elapsed_ms']:8.0f}ms ({pct:5.1f}%) {bar} │ {a['llm_mode']}")

print(f"\n  反向传播:")
print(f"    奖励值: {report['backward']['reward']:.3f}")
print(f"    耗时: {report['backward']['elapsed_ms']:.0f}ms")
print(f"    更新权重: {len(report['backward']['updated_weights'])}个Agent")

print(f"\n  迭代循环:")
print(f"    总轮数: {report['iteration']['total_rounds']}")
print(f"    最终状态: {report['iteration']['final_status']}")

# 保存报告
report["summary"] = {
    "total_elapsed_ms": total_elapsed,
    "all_success": all_success,
    "agents_count": len(report["agents"]),
    "agents_success": sum(1 for a in report["agents"] if a["status"] == "success"),
}

output_dir = Path("task_output") / "comprehensive_verify"
output_dir.mkdir(parents=True, exist_ok=True)
report_path = output_dir / "agent_detail_report.json"
report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"\n  报告已保存: {report_path}")

if all_success:
    print(f"\n  🎉 所有Agent验证通过！全链路端到端成功。")
else:
    print(f"\n  ⚠️ 部分Agent失败，请检查上方详情。")
