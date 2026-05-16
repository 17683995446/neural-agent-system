"""
端到端细颗粒度验证 - 直接调用服务层（不依赖HTTP服务进程）
"""
import json
import shutil
import tempfile
import time
from pathlib import Path

from app.services.convolution.service import ConvolutionLayerService
from app.services.pooling.service import PoolingLayerService
from app.services.fullconnect.service_fc1 import GlobalUnderstandingService
from app.services.fullconnect.service_fc2 import CodeGenerationService
from app.services.fullconnect.service_fc3 import TestGenerationService
from app.services.output.service import OutputLayerService
from app.services.backward.service import BackwardPropagationService

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
    task_id = "e2e_direct_001"
    user_requirement = "Add error handling and input validation to all functions"

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 1: 创建测试代码仓库")
    print("=" * 70)
    # ====================================================================
    tmpdir = tempfile.mkdtemp(prefix="e2e_repo_")
    src = Path(tmpdir) / "src"
    src.mkdir()
    (src / "main.py").write_text(
        'import os\n\ndef process_data(data):\n    """Process input data"""\n    return data\n\ndef validate_input(data):\n    """Validate input"""\n    return bool(data)\n\ndef transform(data):\n    """Transform data"""\n    return [x * 2 for x in data]\n'
    )
    (src / "models.py").write_text(
        'from typing import Optional\n\nclass DataModel:\n    """Data model class"""\n    def __init__(self, name: str, value: Optional[int] = None):\n        self.name = name\n        self.value = value\n\n    def to_dict(self):\n        return {"name": self.name, "value": self.value}\n\nclass ResultModel:\n    """Result model class"""\n    def __init__(self, success: bool, data=None):\n        self.success = success\n        self.data = data\n'
    )
    (src / "utils.py").write_text(
        'import json\nimport logging\n\ndef load_config(path):\n    """Load config from file"""\n    with open(path) as f:\n        return json.load(f)\n\ndef setup_logger(name):\n    """Setup logger"""\n    return logging.getLogger(name)\n'
    )
    print(f"  📁 仓库路径: {tmpdir}")
    print(f"  📄 文件数量: {len(list(Path(tmpdir).rglob('*.*')))}")
    print(f"  🆔 任务ID:   {task_id}")
    print(f"  📝 需求:     {user_requirement}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 2: 卷积层 — ConvolutionLayerService.process_task()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    conv_svc = ConvolutionLayerService()
    conv = conv_svc.process_task(task_id, tmpdir)
    elapsed = (time.time() - t0) * 1000
    s("Conv", "layer = convolution", conv.get("layer") == "convolution", f"got '{conv.get('layer')}'")
    s("Conv", "task_id 匹配", conv.get("task_id") == task_id, f"got '{conv.get('task_id')}'")
    s("Conv", "analyzed_files 存在", "analyzed_files" in conv)
    s("Conv", "failed_files 存在", "failed_files" in conv)
    s("Conv", "summary 存在", "summary" in conv)
    s("Conv", "total_files > 0", conv.get("total_files", 0) > 0, f"got {conv.get('total_files')}")
    s("Conv", "created_at 存在", "created_at" in conv)
    analyzed = conv.get("analyzed_files", [])
    s("Conv", "analyzed_files 非空", len(analyzed) > 0)
    for i, af in enumerate(analyzed):
        fp = af.get("file_path", "?")
        funcs = af.get("functions", [])
        classes = af.get("classes", [])
        imports = af.get("imports", [])
        print(f"       [{i+1}] {Path(fp).name} — {len(funcs)} funcs, {len(classes)} classes, {len(imports)} imports")
        for f in funcs:
            print(f"           func: {f.get('name','?')} (line {f.get('start_line','?')})")
        for c in classes:
            print(f"           class: {c.get('name','?')} (line {c.get('start_line','?')})")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 3: 池化层 — PoolingLayerService.process_task()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    pool_svc = PoolingLayerService()
    pool = pool_svc.process_task(task_id, conv, user_requirement)
    elapsed = (time.time() - t0) * 1000
    s("Pool", "layer = pooling", pool.get("layer") == "pooling")
    s("Pool", "task_id 匹配", pool.get("task_id") == task_id)
    s("Pool", "compressed_features 存在", "compressed_features" in pool)
    s("Pool", "global_features 存在", "global_features" in pool)
    s("Pool", "created_at 存在", "created_at" in pool)
    gf = pool.get("global_features", {})
    s("Pool", "total_files > 0", gf.get("total_files", 0) > 0)
    s("Pool", "total_functions > 0", gf.get("total_functions", 0) > 0)
    print(f"       total_files={gf.get('total_files')}, total_functions={gf.get('total_functions')}, total_classes={gf.get('total_classes')}")
    print(f"       top_functions={[f.get('name') for f in gf.get('top_functions', [])]}")
    print(f"       top_classes={[c.get('name') for c in gf.get('top_classes', [])]}")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 4: FC1 全局理解层 — GlobalUnderstandingService.process_task()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    fc1_svc = GlobalUnderstandingService()
    fc1 = fc1_svc.process_task(task_id, pool, user_requirement)
    elapsed = (time.time() - t0) * 1000
    s("FC1", "layer = global_understanding", fc1.get("layer") == "global_understanding")
    s("FC1", "task_id 匹配", fc1.get("task_id") == task_id)
    sol = fc1.get("solution", {})
    s("FC1", "solution 存在", "solution" in fc1)
    s("FC1", "overview 非空", len(sol.get("overview", "")) > 0)
    s("FC1", "modification_list 存在", "modification_list" in sol)
    s("FC1", "execution_order 存在", "execution_order" in sol)
    s("FC1", "risk_points 存在", "risk_points" in sol)
    s("FC1", "architecture 存在", "architecture" in sol)
    s("FC1", "created_at 存在", "created_at" in fc1)
    mods = sol.get("modification_list", [])
    print(f"       overview: {sol.get('overview','')[:80]}...")
    print(f"       modifications: {len(mods)} 项")
    for i, m in enumerate(mods[:5]):
        print(f"         [{i+1}] type={m.get('type')}, target={m.get('target')}, file={m.get('file')}, priority={m.get('priority')}")
    if len(mods) > 5:
        print(f"         ... 还有 {len(mods)-5} 项")
    print(f"       execution_order: {sol.get('execution_order', [])[:5]}")
    print(f"       risk_points: {len(sol.get('risk_points', []))} 项")
    print(f"       architecture.main_components: {sol.get('architecture',{}).get('main_components',[])}")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 5: FC2 代码生成层 — CodeGenerationService.process_task()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    fc2_svc = CodeGenerationService()
    fc2 = fc2_svc.process_task(task_id, fc1, tmpdir)
    elapsed = (time.time() - t0) * 1000
    s("FC2", "layer = code_generation", fc2.get("layer") == "code_generation")
    s("FC2", "task_id 匹配", fc2.get("task_id") == task_id)
    s("FC2", "modifications 存在", "modifications" in fc2)
    s("FC2", "summary 存在", "summary" in fc2)
    s("FC2", "created_at 存在", "created_at" in fc2)
    summ = fc2.get("summary", {})
    s("FC2", "total >= 0", summ.get("total_modifications", -1) >= 0)
    s("FC2", "successful + failed = total", summ.get("successful",0)+summ.get("failed",0)==summ.get("total_modifications",-1))
    modifications = fc2.get("modifications", [])
    print(f"       total: {summ.get('total_modifications')}, success: {summ.get('successful')}, failed: {summ.get('failed')}")
    for i, m in enumerate(modifications[:5]):
        print(f"         [{i+1}] target={m.get('target')}, status={m.get('status')}, syntax_valid={m.get('syntax_valid','?')}, trust={m.get('trust_level','?')}")
    if len(modifications) > 5:
        print(f"         ... 还有 {len(modifications)-5} 项")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 6: FC3 测试生成层 — TestGenerationService.process_task()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    fc3_svc = TestGenerationService()
    fc3 = fc3_svc.process_task(task_id, fc2)
    elapsed = (time.time() - t0) * 1000
    s("FC3", "layer = test_generation", fc3.get("layer") == "test_generation")
    s("FC3", "task_id 匹配", fc3.get("task_id") == task_id)
    s("FC3", "tests 存在", "tests" in fc3)
    s("FC3", "coverage 存在", "coverage" in fc3)
    s("FC3", "summary 存在", "summary" in fc3)
    s("FC3", "created_at 存在", "created_at" in fc3)
    summ3 = fc3.get("summary", {})
    cov = fc3.get("coverage", {})
    tests = fc3.get("tests", [])
    print(f"       total_tests: {summ3.get('total_tests')}, unit: {summ3.get('unit_tests')}, integration: {summ3.get('integration_tests')}")
    print(f"       coverage: {cov.get('coverage_percent',0)}%, total_lines: {cov.get('total_lines')}, covered_lines: {cov.get('covered_lines')}")
    for i, t_item in enumerate(tests[:5]):
        print(f"         [{i+1}] type={t_item.get('test_type')}, name={t_item.get('test_name','?')[:40]}, target={t_item.get('target','?')}")
    if len(tests) > 5:
        print(f"         ... 还有 {len(tests)-5} 项")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 7: 输出层 — OutputLayerService.process_task()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    out_svc = OutputLayerService()
    output = out_svc.process_task(task_id, user_requirement, fc1, fc2, fc3, 1500.0)
    elapsed = (time.time() - t0) * 1000
    s("Output", "layer = output", output.get("layer") == "output")
    s("Output", "task_id 匹配", output.get("task_id") == task_id)
    s("Output", "document_path 存在", "document_path" in output)
    doc_path = output.get("document_path", "")
    if doc_path:
        p = Path(doc_path)
        s("Output", "文件存在", p.exists())
        if p.exists():
            content = p.read_text(encoding="utf-8")
            s("Output", "文件非空", len(content) > 0, f"size={len(content)}")
            s("Output", "Markdown标题开头", content.startswith("#"))
            s("Output", "包含任务ID", task_id in content)
            lines = content.split("\n")
            headings = [l for l in lines if l.startswith("#")]
            print(f"       文件大小: {len(content)} chars, {len(lines)} lines, {len(headings)} headings")
            for h in headings[:8]:
                print(f"         {h}")
            if len(headings) > 8:
                print(f"         ... 还有 {len(headings)-8} 个标题")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 8: 反向传播 — BackwardPropagationService.process_user_feedback()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    bw_svc = BackwardPropagationService()
    bw = bw_svc.process_user_feedback(task_id, {
        "satisfaction_score": 4.5,
        "feedback_items": [
            {"type": "positive", "description": "Good code modifications"},
            {"type": "suggestion", "description": "Could add more tests"},
        ],
        "comments": "Results look good overall",
        "iteration_number": 1,
    })
    elapsed = (time.time() - t0) * 1000
    s("Backward", "layer = backward_propagation", bw.get("layer") == "backward_propagation")
    s("Backward", "task_id 匹配", bw.get("task_id") == task_id)
    s("Backward", "reward 存在", "reward" in bw)
    reward = bw.get("reward", 0)
    s("Backward", "reward ∈ [-1, 1]", -1.0 <= reward <= 1.0, f"reward={reward:.4f}")
    s("Backward", "updated_weights 存在", "updated_weights" in bw)
    uw = bw.get("updated_weights", {})
    print(f"       reward: {reward:.4f}")
    print(f"       更新权重数: {len(uw)}")
    for agent_id in list(uw.keys())[:6]:
        w = uw[agent_id]
        print(f"         {agent_id}: {json.dumps(w, ensure_ascii=False)[:80]}")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 9: 计算层奖励 — BackwardPropagationService.calculate_layer_rewards()")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    rewards = bw_svc.calculate_layer_rewards(task_id, {"satisfaction_score": 5})
    elapsed = (time.time() - t0) * 1000
    s("Rewards", "包含6层", len(rewards) >= 6, f"got {len(rewards)}")
    for layer_name in ["convolution", "pooling", "global_understanding", "code_generation", "test_generation", "output"]:
        s("Rewards", f"包含 {layer_name}", layer_name in rewards)
    s("Rewards", "output奖励 >= convolution奖励", rewards.get("output",0) >= rewards.get("convolution",0))
    for layer_name, reward_val in sorted(rewards.items()):
        print(f"       {layer_name}: {reward_val:.4f}")
    print(f"  ⏱  耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 10: 输出文件完整性验证")
    print("=" * 70)
    # ====================================================================
    task_dir = Path("task_output") / task_id
    expected_files = [
        ("convolution/analysis_results.json", "json"),
        ("pooling/pooling_results.json", "json"),
        ("global_understanding/solution.json", "json"),
        ("code_generation/modifications.json", "json"),
        ("test_generation/test_cases.json", "json"),
        ("output/task_report.md", "markdown"),
    ]
    for rel_path, fmt in expected_files:
        fp = task_dir / rel_path
        s("Files", f"存在: {rel_path}", fp.exists(), f"path: {fp}")
        if fp.exists():
            file_size = fp.stat().st_size
            print(f"         文件大小: {file_size} bytes")
            if fmt == "json":
                data = json.loads(fp.read_text(encoding="utf-8"))
                s("Files", f"JSON有效: {rel_path}", True)
                s("Files", f"task_id正确: {rel_path}", data.get("task_id") == task_id)
                s("Files", f"layer存在: {rel_path}", "layer" in data)
                print(f"         layer: {data.get('layer')}, created_at: {data.get('created_at','?')[:19]}")
            elif fmt == "markdown":
                content = fp.read_text(encoding="utf-8")
                s("Files", f"MD非空: {rel_path}", len(content) > 0)
                s("Files", f"MD以#开头: {rel_path}", content.startswith("#"))
                line_count = len(content.split("\n"))
                heading_count = len([l for l in content.split("\n") if l.startswith("#")])
                print(f"         行数: {line_count}, 标题数: {heading_count}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 11: 层间数据流一致性验证")
    print("=" * 70)
    # ====================================================================
    s("Flow", "所有层task_id一致",
        conv.get("task_id")==task_id and pool.get("task_id")==task_id and
        fc1.get("task_id")==task_id and fc2.get("task_id")==task_id and
        fc3.get("task_id")==task_id and output.get("task_id")==task_id)
    s("Flow", "层序: conv→pool→fc1→fc2→fc3→output",
        conv.get("layer")=="convolution" and pool.get("layer")=="pooling" and
        fc1.get("layer")=="global_understanding" and fc2.get("layer")=="code_generation" and
        fc3.get("layer")=="test_generation" and output.get("layer")=="output")
    fc1_mods = len(fc1.get("solution",{}).get("modification_list",[]))
    fc2_total = fc2.get("summary",{}).get("total_modifications",-1)
    s("Flow", "FC1修改数==FC2总数", fc1_mods==fc2_total, f"FC1={fc1_mods}, FC2={fc2_total}")
    s("Flow", "FC2成功数>=0", fc2.get("summary",{}).get("successful",-1)>=0)
    s("Flow", "FC3测试数>=0", fc3.get("summary",{}).get("total_tests",-1)>=0)

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
