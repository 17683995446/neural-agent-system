"""
迭代循环验证测试 - 验证前向→反馈→反向→继续/停止 的完整迭代流程
"""
import json
import shutil
import tempfile
import time
from pathlib import Path

from app.services.pipeline.neural_pipeline import NeuralNetworkPipeline
from app.services.pipeline.iteration_manager import (
    get_iteration_manager,
)

total_pass = 0
total_fail = 0


def s(group, name, condition, detail=""):
    global total_pass, total_fail
    icon = "✅" if condition else "❌"
    msg = f"  {icon} [{group}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if condition:
        total_pass += 1
    else:
        total_fail += 1
    return condition


def main():
    task_id = "iter_test_001"
    user_requirement = "Add error handling to all functions"
    max_iteration = 3

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 1: 创建测试代码仓库")
    print("=" * 70)
    # ====================================================================
    tmpdir = tempfile.mkdtemp(prefix="iter_repo_")
    src = Path(tmpdir) / "src"
    src.mkdir()
    (src / "main.py").write_text(
        'import os\n\ndef process_data(data):\n    return data\n\ndef validate_input(data):\n    return bool(data)\n'
    )
    (src / "models.py").write_text(
        'class DataModel:\n    def __init__(self, name):\n        self.name = name\n'
    )
    print(f"  📁 仓库: {tmpdir}")
    print(f"  🆔 任务: {task_id}, max_iteration={max_iteration}")

    pipeline = NeuralNetworkPipeline()

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 2: 启动迭代式Pipeline — 第1轮前向传播")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    result = pipeline.start_iterative_pipeline(
        task_id=task_id,
        user_requirement=user_requirement,
        code_repo_path=tmpdir,
        max_iteration=max_iteration,
    )
    elapsed = (time.time() - t0) * 1000

    s("Init", "返回task_id", result.get("task_id") == task_id)
    s("Init", "iteration=1", result.get("iteration") == 1)
    s("Init", "status=awaiting_feedback", result.get("status") == "awaiting_feedback")
    s("Init", "forward_result存在", "forward_result" in result)
    s("Init", "session_state存在", "session_state" in result)
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # 验证迭代状态文件
    state_file = Path("task_output") / task_id / "iterations" / "iteration_state.json"
    s("Init", "迭代状态文件已保存", state_file.exists())
    if state_file.exists():
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        s("Init", "状态文件current_iteration=1", state_data.get("current_iteration") == 1)
        s("Init", "状态文件status=awaiting_feedback", state_data.get("status") == "awaiting_feedback")
        print(f"       status={state_data.get('status')}, iteration={state_data.get('current_iteration')}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 3: 提交反馈(不满意,继续) → 反向传播 → 第2轮前向传播")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    result2 = pipeline.process_iteration_feedback(
        task_id=task_id,
        feedback={
            "satisfaction_score": 3.0,
            "stop_iteration": False,
            "feedback_items": [{"type": "suggestion", "description": "Need more tests"}],
            "comments": "Not satisfied yet",
        },
    )
    elapsed = (time.time() - t0) * 1000

    s("Iter2", "返回task_id", result2.get("task_id") == task_id)
    s("Iter2", "iteration=2", result2.get("iteration") == 2, f"got {result2.get('iteration')}")
    s("Iter2", "status=awaiting_feedback", result2.get("status") == "awaiting_feedback")
    s("Iter2", "backward_result存在", "backward_result" in result2)
    s("Iter2", "forward_result存在", "forward_result" in result2)
    bw = result2.get("backward_result", {})
    s("Iter2", "backward reward∈[-1,1]", -1.0 <= bw.get("reward", 0) <= 1.0, f"reward={bw.get('reward')}")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")
    print(f"       backward reward={bw.get('reward', 0):.4f}")

    # 验证迭代状态
    if state_file.exists():
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        s("Iter2", "状态文件current_iteration=2", state_data.get("current_iteration") == 2)
        s("Iter2", "状态文件2轮迭代记录", len(state_data.get("iterations", [])) == 2)
        print(f"       iterations count={len(state_data.get('iterations', []))}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 4: 提交反馈(满意,停止) → 反向传播 → 迭代结束")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    result3 = pipeline.process_iteration_feedback(
        task_id=task_id,
        feedback={
            "satisfaction_score": 5.0,
            "stop_iteration": True,
            "feedback_items": [{"type": "positive", "description": "Excellent results"}],
            "comments": "Very satisfied now",
        },
    )
    elapsed = (time.time() - t0) * 1000

    s("Stop", "返回task_id", result3.get("task_id") == task_id)
    s("Stop", "iteration=2 (未增加)", result3.get("iteration") == 2, f"got {result3.get('iteration')}")
    s("Stop", "status=completed", result3.get("status") == "completed")
    s("Stop", "backward_result存在", "backward_result" in result3)
    s("Stop", "message包含'迭代结束'", "迭代结束" in result3.get("message", ""))
    print(f"  ⏱  耗时: {elapsed:.0f}ms")
    print(f"       message: {result3.get('message')}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 5: 验证迭代状态最终一致性")
    print("=" * 70)
    # ====================================================================
    session = get_iteration_manager().get_session(task_id)
    s("Final", "会话存在", session is not None)
    if session:
        s("Final", "current_iteration=2", session.current_iteration == 2)
        s("Final", "status=completed", session.status == "completed")
        s("Final", "should_continue=False", session.should_continue is False)
        s("Final", "iterations记录数=2", len(session.iterations) == 2)
        s("Final", "第1轮有forward+backward", 
            session.iterations[0].forward_result is not None and session.iterations[0].backward_result is not None)
        s("Final", "第2轮有forward+backward",
            session.iterations[1].forward_result is not None and session.iterations[1].backward_result is not None)
        print(f"       iterations: {len(session.iterations)}")
        for it in session.iterations:
            has_fwd = it.forward_result is not None
            has_bwd = it.backward_result is not None
            has_fb = it.user_feedback is not None
            print(f"         iter {it.iteration}: forward={has_fwd}, feedback={has_fb}, backward={has_bwd}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 6: 验证输出文件")
    print("=" * 70)
    # ====================================================================
    s("Files", "迭代状态文件存在", state_file.exists())
    if state_file.exists():
        final_state = json.loads(state_file.read_text(encoding="utf-8"))
        s("Files", "最终status=completed", final_state.get("status") == "completed")
        s("Files", "最终iteration=2", final_state.get("current_iteration") == 2)
        print(f"       final status={final_state.get('status')}, iteration={final_state.get('current_iteration')}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 7: 测试达到最大迭代次数自动停止")
    print("=" * 70)
    # ====================================================================
    task_id2 = "iter_test_002"
    result_a = pipeline.start_iterative_pipeline(
        task_id=task_id2,
        user_requirement=user_requirement,
        code_repo_path=tmpdir,
        max_iteration=2,
    )
    s("MaxIter", "第1轮启动成功", result_a.get("iteration") == 1)

    result_b = pipeline.process_iteration_feedback(
        task_id=task_id2,
        feedback={"satisfaction_score": 2.0, "stop_iteration": False},
    )
    s("MaxIter", "第2轮启动成功", result_b.get("iteration") == 2)
    s("MaxIter", "第2轮等待反馈", result_b.get("status") == "awaiting_feedback")

    result_c = pipeline.process_iteration_feedback(
        task_id=task_id2,
        feedback={"satisfaction_score": 3.0, "stop_iteration": False},
    )
    s("MaxIter", "达到max_iteration自动停止", result_c.get("status") == "completed")
    s("MaxIter", "最终iteration=2", result_c.get("iteration") == 2)
    print(f"       status={result_c.get('status')}, message={result_c.get('message')}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 8: 测试satisfaction_score>=5自动停止")
    print("=" * 70)
    # ====================================================================
    task_id3 = "iter_test_003"
    result_x = pipeline.start_iterative_pipeline(
        task_id=task_id3,
        user_requirement=user_requirement,
        code_repo_path=tmpdir,
        max_iteration=10,
    )
    s("HighScore", "第1轮启动成功", result_x.get("iteration") == 1)

    result_y = pipeline.process_iteration_feedback(
        task_id=task_id3,
        feedback={"satisfaction_score": 5.0, "stop_iteration": False},
    )
    s("HighScore", "satisfaction=5自动停止", result_y.get("status") == "completed")
    print(f"       status={result_y.get('status')}, message={result_y.get('message')}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 9: 测试强制停止迭代")
    print("=" * 70)
    # ====================================================================
    task_id4 = "iter_test_004"
    pipeline.start_iterative_pipeline(
        task_id=task_id4,
        user_requirement=user_requirement,
        code_repo_path=tmpdir,
        max_iteration=10,
    )
    stop_result = pipeline.stop_iteration(task_id4)
    s("ForceStop", "强制停止成功", stop_result.get("status") == "completed")
    s("ForceStop", "message包含'强制停止'", "强制停止" in stop_result.get("message", ""))
    print(f"       status={stop_result.get('status')}, message={stop_result.get('message')}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 10: 测试迭代状态查询")
    print("=" * 70)
    # ====================================================================
    status1 = pipeline.get_iteration_status(task_id)
    s("Status", "查询成功", "task_id" in status1)
    s("Status", "status=completed", status1.get("status") == "completed")

    mgr = get_iteration_manager()
    sessions = mgr.list_sessions()
    s("Status", "会话列表非空", len(sessions) >= 4, f"got {len(sessions)}")
    print(f"       sessions count: {len(sessions)}")

    shutil.rmtree(tmpdir, ignore_errors=True)

    # ====================================================================
    print("\n" + "=" * 70)
    print("  最终汇总")
    print("=" * 70)
    print(f"  ✅ 通过: {total_pass}")
    print(f"  ❌ 失败: {total_fail}")
    print(f"  📊 总计: {total_pass + total_fail}")
    print(f"  📈 通过率: {total_pass / (total_pass + total_fail) * 100:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
