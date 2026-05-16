"""
端到端细颗粒度验证 - 每个步骤详细打印
"""
import json
import shutil
import tempfile
import time
from pathlib import Path

BASE = "http://localhost:8322"

def http_get(path, params=None):
    import urllib.request, urllib.parse, urllib.error
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {"error": str(e)}
        return e.code, body
    except Exception as e:
        return 500, {"error": str(e)}

def http_post(path, data=None, params=None):
    import urllib.request, urllib.parse, urllib.error
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(data).encode("utf-8") if data else b"{}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            error_body = json.loads(e.read())
        except Exception:
            error_body = {"error": str(e)}
        return e.code, error_body
    except Exception as e:
        return 500, {"error": str(e)}


def step(group, name, condition, detail=""):
    icon = "✅" if condition else "❌"
    msg = f"  {icon} [{group}] {name}"
    if not condition and detail:
        msg += f" — {detail}"
    elif condition and detail:
        msg += f" — {detail}"
    print(msg)
    return condition


def main():
    total_pass = 0
    total_fail = 0

    def s(group, name, condition, detail=""):
        nonlocal total_pass, total_fail
        if condition:
            total_pass += 1
        else:
            total_fail += 1
        return step(group, name, condition, detail)

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 1: 健康检查 — GET /health")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, data = http_get("/health")
    elapsed = (time.time() - t0) * 1000
    s("Health", "HTTP状态码 = 200", status == 200, f"status={status}")
    s("Health", "响应status字段 = healthy", data.get("status") == "healthy", f"got '{data.get('status')}'")
    s("Health", "响应version字段 = 1.0.0", data.get("version") == "1.0.0", f"got '{data.get('version')}'")
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 2: 创建测试代码仓库")
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
    task_id = "e2e_http_002"
    user_requirement = "Add error handling and input validation to all functions"
    file_count = len(list(Path(tmpdir).rglob("*.*")))
    print(f"  📁 仓库路径: {tmpdir}")
    print(f"  📄 文件数量: {file_count}")
    print(f"  🆔 任务ID:   {task_id}")
    print(f"  📝 需求:     {user_requirement}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 3: 卷积层 — POST /api/v1/convolution/process")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, conv_data = http_post("/api/v1/convolution/process", {
        "task_id": task_id,
        "code_repo_path": tmpdir,
    })
    elapsed = (time.time() - t0) * 1000
    s("Conv", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("Conv", "layer = convolution", conv_data.get("layer") == "convolution", f"got '{conv_data.get('layer')}'")
        s("Conv", "task_id 匹配", conv_data.get("task_id") == task_id, f"got '{conv_data.get('task_id')}'")
        s("Conv", "analyzed_files 存在", "analyzed_files" in conv_data)
        s("Conv", "failed_files 存在", "failed_files" in conv_data)
        s("Conv", "summary 存在", "summary" in conv_data)
        s("Conv", "total_files > 0", conv_data.get("total_files", 0) > 0, f"got {conv_data.get('total_files')}")
        analyzed = conv_data.get("analyzed_files", [])
        s("Conv", "analyzed_files 非空", len(analyzed) > 0)
        for i, af in enumerate(analyzed):
            fp = af.get("file_path", "?")
            funcs = af.get("functions", [])
            classes = af.get("classes", [])
            imports = af.get("imports", [])
            print(f"       [{i+1}] {Path(fp).name} — {len(funcs)} funcs, {len(classes)} classes, {len(imports)} imports")
            for f in funcs:
                print(f"           func: {f.get('name', '?')} (line {f.get('start_line', '?')})")
            for c in classes:
                print(f"           class: {c.get('name', '?')} (line {c.get('start_line', '?')})")
        s("Conv", "created_at 存在", "created_at" in conv_data)
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 4: 池化层 — POST /api/v1/pooling/process")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, pool_data = http_post("/api/v1/pooling/process", {
        "task_id": task_id,
        "convolution_output": conv_data,
        "user_requirement": user_requirement,
    })
    elapsed = (time.time() - t0) * 1000
    s("Pool", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("Pool", "layer = pooling", pool_data.get("layer") == "pooling")
        s("Pool", "task_id 匹配", pool_data.get("task_id") == task_id)
        s("Pool", "compressed_features 存在", "compressed_features" in pool_data)
        s("Pool", "global_features 存在", "global_features" in pool_data)
        gf = pool_data.get("global_features", {})
        s("Pool", "global_features.total_files > 0", gf.get("total_files", 0) > 0, f"got {gf.get('total_files')}")
        s("Pool", "global_features.total_functions > 0", gf.get("total_functions", 0) > 0, f"got {gf.get('total_functions')}")
        print(f"       total_files: {gf.get('total_files')}")
        print(f"       total_functions: {gf.get('total_functions')}")
        print(f"       total_classes: {gf.get('total_classes')}")
        print(f"       unique_imports: {gf.get('unique_imports')}")
        print(f"       top_functions: {[f.get('name') for f in gf.get('top_functions', [])]}")
        print(f"       top_classes: {[c.get('name') for c in gf.get('top_classes', [])]}")
        s("Pool", "created_at 存在", "created_at" in pool_data)
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 5: FC1 全局理解层 — POST /api/v1/fullconnect/fc1/process")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, fc1_data = http_post("/api/v1/fullconnect/fc1/process", {
        "task_id": task_id,
        "pooling_output": pool_data,
        "user_requirement": user_requirement,
    })
    elapsed = (time.time() - t0) * 1000
    s("FC1", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("FC1", "layer = global_understanding", fc1_data.get("layer") == "global_understanding")
        s("FC1", "task_id 匹配", fc1_data.get("task_id") == task_id)
        sol = fc1_data.get("solution", {})
        s("FC1", "solution 存在", "solution" in fc1_data)
        s("FC1", "overview 非空", len(sol.get("overview", "")) > 0)
        s("FC1", "modification_list 存在", "modification_list" in sol)
        s("FC1", "execution_order 存在", "execution_order" in sol)
        s("FC1", "risk_points 存在", "risk_points" in sol)
        s("FC1", "architecture 存在", "architecture" in sol)
        mods = sol.get("modification_list", [])
        print(f"       overview: {sol.get('overview', '')[:80]}...")
        print(f"       modifications: {len(mods)} 项")
        for i, m in enumerate(mods[:5]):
            print(f"         [{i+1}] type={m.get('type')}, target={m.get('target')}, file={m.get('file')}, priority={m.get('priority')}")
        if len(mods) > 5:
            print(f"         ... 还有 {len(mods)-5} 项")
        print(f"       execution_order: {sol.get('execution_order', [])[:5]}...")
        print(f"       risk_points: {len(sol.get('risk_points', []))} 项")
        arch = sol.get("architecture", {})
        print(f"       architecture.main_components: {arch.get('main_components', [])}")
        s("FC1", "created_at 存在", "created_at" in fc1_data)
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 6: FC2 代码生成层 — POST /api/v1/fullconnect/fc2/process")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, fc2_data = http_post("/api/v1/fullconnect/fc2/process", {
        "task_id": task_id,
        "fc1_output": fc1_data,
        "code_repo_path": tmpdir,
    })
    elapsed = (time.time() - t0) * 1000
    s("FC2", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("FC2", "layer = code_generation", fc2_data.get("layer") == "code_generation")
        s("FC2", "task_id 匹配", fc2_data.get("task_id") == task_id)
        s("FC2", "modifications 存在", "modifications" in fc2_data)
        s("FC2", "summary 存在", "summary" in fc2_data)
        summ = fc2_data.get("summary", {})
        s("FC2", "summary.total_modifications >= 0", summ.get("total_modifications", -1) >= 0)
        s("FC2", "summary.successful + failed = total", summ.get("successful", 0) + summ.get("failed", 0) == summ.get("total_modifications", -1))
        modifications = fc2_data.get("modifications", [])
        print(f"       total: {summ.get('total_modifications')}, success: {summ.get('successful')}, failed: {summ.get('failed')}")
        for i, m in enumerate(modifications[:5]):
            valid = m.get("syntax_valid", "?")
            trust = m.get("trust_level", "?")
            print(f"         [{i+1}] target={m.get('target')}, status={m.get('status')}, syntax_valid={valid}, trust={trust}")
        if len(modifications) > 5:
            print(f"         ... 还有 {len(modifications)-5} 项")
        s("FC2", "created_at 存在", "created_at" in fc2_data)
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 7: FC3 测试生成层 — POST /api/v1/fullconnect/fc3/process")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, fc3_data = http_post("/api/v1/fullconnect/fc3/process", {
        "task_id": task_id,
        "fc2_output": fc2_data,
    })
    elapsed = (time.time() - t0) * 1000
    s("FC3", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("FC3", "layer = test_generation", fc3_data.get("layer") == "test_generation")
        s("FC3", "task_id 匹配", fc3_data.get("task_id") == task_id)
        s("FC3", "tests 存在", "tests" in fc3_data)
        s("FC3", "coverage 存在", "coverage" in fc3_data)
        s("FC3", "summary 存在", "summary" in fc3_data)
        summ3 = fc3_data.get("summary", {})
        cov = fc3_data.get("coverage", {})
        tests = fc3_data.get("tests", [])
        print(f"       total_tests: {summ3.get('total_tests')}, unit: {summ3.get('unit_tests')}, integration: {summ3.get('integration_tests')}")
        print(f"       coverage: {cov.get('coverage_percent', 0)}%, total_lines: {cov.get('total_lines')}, covered_lines: {cov.get('covered_lines')}")
        for i, t in enumerate(tests[:5]):
            print(f"         [{i+1}] type={t.get('test_type')}, name={t.get('test_name', '?')[:40]}, target={t.get('target', '?')}")
        if len(tests) > 5:
            print(f"         ... 还有 {len(tests)-5} 项")
        s("FC3", "created_at 存在", "created_at" in fc3_data)
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 8: 输出层 — POST /api/v1/output/generate")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, output_data = http_post("/api/v1/output/generate", {
        "task_id": task_id,
        "user_requirement": user_requirement,
        "fc1_output": fc1_data,
        "fc2_output": fc2_data,
        "fc3_output": fc3_data,
        "execution_time_ms": 1500.0,
    })
    elapsed = (time.time() - t0) * 1000
    s("Output", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("Output", "layer = output", output_data.get("layer") == "output")
        s("Output", "task_id 匹配", output_data.get("task_id") == task_id)
        s("Output", "document_path 存在", "document_path" in output_data)
        doc_path = output_data.get("document_path", "")
        if doc_path:
            p = Path(doc_path)
            s("Output", "文件存在", p.exists(), f"path: {doc_path}")
            if p.exists():
                content = p.read_text(encoding="utf-8")
                s("Output", "文件非空", len(content) > 0, f"size={len(content)}")
                s("Output", "Markdown标题开头", content.startswith("#"), f"first 20: {content[:20]}")
                s("Output", "包含任务ID", task_id in content)
                s("Output", "包含用户需求", user_requirement[:20] in content)
                lines = content.split("\n")
                headings = [l for l in lines if l.startswith("#")]
                print(f"       文件大小: {len(content)} chars, {len(lines)} lines")
                print(f"       标题数量: {len(headings)}")
                for h in headings[:8]:
                    print(f"         {h}")
                if len(headings) > 8:
                    print(f"         ... 还有 {len(headings)-8} 个标题")
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 9: 反向传播 — POST /api/v1/backward/feedback")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, bw_data = http_post("/api/v1/backward/feedback", {
        "task_id": task_id,
        "satisfaction_score": 4.5,
        "feedback_items": [
            {"type": "positive", "description": "Good code modifications"},
            {"type": "suggestion", "description": "Could add more tests"},
        ],
        "comments": "Results look good overall",
        "iteration_number": 1,
    })
    elapsed = (time.time() - t0) * 1000
    s("Backward", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("Backward", "layer = backward_propagation", bw_data.get("layer") == "backward_propagation")
        s("Backward", "task_id 匹配", bw_data.get("task_id") == task_id)
        s("Backward", "reward 存在", "reward" in bw_data)
        reward = bw_data.get("reward", 0)
        s("Backward", "reward ∈ [-1, 1]", -1.0 <= reward <= 1.0, f"reward={reward}")
        s("Backward", "updated_weights 存在", "updated_weights" in bw_data)
        s("Backward", "feedback_summary 存在", "feedback_summary" in bw_data)
        uw = bw_data.get("updated_weights", {})
        print(f"       reward: {reward:.4f}")
        print(f"       更新权重数: {len(uw)}")
        for agent_id, weights in list(uw.items())[:5]:
            print(f"         {agent_id}: {json.dumps(weights, ensure_ascii=False)[:80]}")
        fs = bw_data.get("feedback_summary", {})
        print(f"       feedback_summary: satisfaction={fs.get('satisfaction_score')}, items={fs.get('feedback_count')}")
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 10: 计算层奖励 — POST /api/v1/backward/calculate-rewards")
    print("=" * 70)
    # ====================================================================
    t0 = time.time()
    status, rewards_data = http_post("/api/v1/backward/calculate-rewards",
        params={"task_id": task_id},
        data={"satisfaction_score": 5},
    )
    elapsed = (time.time() - t0) * 1000
    s("Rewards", "HTTP状态码 = 200", status == 200, f"status={status}")
    if status == 200:
        s("Rewards", "layer_rewards 存在", "layer_rewards" in rewards_data)
        lr = rewards_data.get("layer_rewards", {})
        s("Rewards", "包含 convolution", "convolution" in lr)
        s("Rewards", "包含 pooling", "pooling" in lr)
        s("Rewards", "包含 global_understanding", "global_understanding" in lr)
        s("Rewards", "包含 code_generation", "code_generation" in lr)
        s("Rewards", "包含 test_generation", "test_generation" in lr)
        s("Rewards", "包含 output", "output" in lr)
        s("Rewards", "output奖励 >= convolution奖励", lr.get("output", 0) >= lr.get("convolution", 0))
        for layer_name, reward_val in sorted(lr.items()):
            print(f"       {layer_name}: {reward_val:.4f}")
    print(f"  ⏱  响应耗时: {elapsed:.0f}ms")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 11: 输出文件完整性验证")
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
        exists = fp.exists()
        s("Files", f"存在: {rel_path}", exists, f"path: {fp}")
        if exists:
            file_size = fp.stat().st_size
            print(f"         文件大小: {file_size} bytes")
            if fmt == "json":
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    s("Files", f"JSON有效: {rel_path}", True)
                    s("Files", f"JSON.task_id正确: {rel_path}", data.get("task_id") == task_id, f"got '{data.get('task_id')}'")
                    s("Files", f"JSON.layer存在: {rel_path}", "layer" in data)
                    print(f"         layer: {data.get('layer')}, created_at: {data.get('created_at', '?')[:19]}")
                except Exception as e:
                    s("Files", f"JSON有效: {rel_path}", False, str(e))
            elif fmt == "markdown":
                content = fp.read_text(encoding="utf-8")
                s("Files", f"MD非空: {rel_path}", len(content) > 0)
                s("Files", f"MD以#开头: {rel_path}", content.startswith("#"))
                line_count = len(content.split("\n"))
                heading_count = len([l for l in content.split("\n") if l.startswith("#")])
                print(f"         行数: {line_count}, 标题数: {heading_count}")

    # ====================================================================
    print("\n" + "=" * 70)
    print("  STEP 12: 层间数据流一致性验证")
    print("=" * 70)
    # ====================================================================
    s("Flow", "所有层task_id一致",
        conv_data.get("task_id") == task_id and
        pool_data.get("task_id") == task_id and
        fc1_data.get("task_id") == task_id and
        fc2_data.get("task_id") == task_id and
        fc3_data.get("task_id") == task_id and
        output_data.get("task_id") == task_id)

    s("Flow", "层序正确: conv→pool→fc1→fc2→fc3→output",
        conv_data.get("layer") == "convolution" and
        pool_data.get("layer") == "pooling" and
        fc1_data.get("layer") == "global_understanding" and
        fc2_data.get("layer") == "code_generation" and
        fc3_data.get("layer") == "test_generation" and
        output_data.get("layer") == "output")

    s("Flow", "FC1修改数 == FC2总数",
        len(fc1_data.get("solution", {}).get("modification_list", [])) == fc2_data.get("summary", {}).get("total_modifications", -1),
        f"FC1={len(fc1_data.get('solution', {}).get('modification_list', []))}, FC2={fc2_data.get('summary', {}).get('total_modifications')}")

    s("Flow", "FC2成功数 >= 0",
        fc2_data.get("summary", {}).get("successful", -1) >= 0,
        f"got {fc2_data.get('summary', {}).get('successful')}")

    s("Flow", "FC3测试数 >= 0",
        fc3_data.get("summary", {}).get("total_tests", -1) >= 0,
        f"got {fc3_data.get('summary', {}).get('total_tests')}")

    # 清理
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
    return total_fail == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
