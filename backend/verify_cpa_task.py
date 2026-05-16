"""
CPA考试刷题网页 - 真实任务验证
使用Neural Agent System从需求出发生成完整项目
"""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

# 限制并发避免LLM限频
os.environ["MAX_CONCURRENT_MODS"] = "2"
os.environ["MAX_CONCURRENT_TESTS"] = "2"

TASK_ID = f"cpa_exam_app_{int(time.time())}"
USER_REQUIREMENT = """实现一个CPA考试刷题网页应用，功能包括：
1. 题目展示：支持单选题、多选题、判断题，每题显示题干、选项、答案解析
2. 刷题模式：顺序刷题、随机刷题、错题重做、收藏题目
3. 答题统计：正确率、刷题数量、用时统计、薄弱知识点分析
4. 知识点分类：按会计、审计、财管、税法、经济法、战略六科分类
5. 用户功能：学习进度保存、错题本、收藏夹、学习计划
6. 界面要求：响应式设计，支持手机和PC端，深色/浅色主题切换
7. 技术栈：HTML + CSS + JavaScript前端，数据用JSON存储"""

CODE_REPO = "D:\\huawei_workspace\\CPA考试刷题APP"


def fmt_dict(d: Any, max_len: int = 300) -> str:
    if d is None:
        return "None"
    s = json.dumps(d, ensure_ascii=False, default=str) if not isinstance(d, str) else d
    return s[:max_len] + "..." if len(s) > max_len else s


def print_agent(layer, agent, status, elapsed_ms, mode, input_desc, output_desc, details=None):
    print(f"\n{'─'*70}")
    print(f"  {layer} | {agent}")
    print(f"  状态: {status} | 耗时: {elapsed_ms/1000:.1f}s | 模式: {mode}")
    print(f"  输入: {input_desc}")
    print(f"  输出: {output_desc}")
    if details:
        for k, v in details.items():
            print(f"  {k}: {v}")


report = {"task_id": TASK_ID, "requirement": USER_REQUIREMENT, "agents": []}


print("=" * 70)
print("  CPA考试刷题网页 - Neural Agent System 真实任务验证")
print("=" * 70)
print(f"  任务: {USER_REQUIREMENT[:50]}...")
print(f"  输出目录: {CODE_REPO}")

# ============================================================
# 执行完整Pipeline
# ============================================================
from app.services.pipeline.neural_pipeline import get_neural_pipeline
from app.core.llm_client import get_llm_client

llm = get_llm_client()
print(f"  LLM: {llm.model} (available={llm.is_available})")

pipeline = get_neural_pipeline()

print(f"\n{'━'*70}")
print(f"  开始执行 Pipeline ...")
print(f"{'━'*70}")

total_start = time.time()

try:
    result = pipeline.execute_forward_pipeline(
        task_id=TASK_ID,
        user_requirement=USER_REQUIREMENT,
        code_repo_path=CODE_REPO,
        max_iteration=1
    )
    total_elapsed = (time.time() - total_start) * 1000
    pipeline_error = None
except Exception as e:
    result = {"error": str(e)}
    total_elapsed = (time.time() - total_start) * 1000
    pipeline_error = str(e)

print(f"\n{'━'*70}")
print(f"  Pipeline 执行完成!")
print(f"{'━'*70}")

# ============================================================
# 分析结果
# ============================================================
layer_outputs = result.get("layer_outputs", {})

# L1 Conv
conv = layer_outputs.get("convolution", {})
conv_files = conv.get("analyzed_files", [])
print_agent("L1 Conv", "ConvolutionService",
    "✅" if "error" not in conv else "❌",
    0, "LLM+Tree-sitter",
    f"代码路径: {CODE_REPO}",
    f"分析{len(conv_files)}个文件")
if conv_files:
    for f in conv_files[:5]:
        print(f"    - {f.get('file_name', 'unknown')} ({f.get('language', '?')})")

# L2 Pool
pool = layer_outputs.get("pooling", {})
compressed = pool.get("compressed_features", [])
print_agent("L2 Pool", "PoolingService",
    "✅" if "error" not in pool else "❌",
    0, "LLM语义压缩",
    f"{len(conv_files)}个分析文件",
    f"压缩为{len(compressed)}个特征")

# L3 FC1
fc1 = layer_outputs.get("fc1_global_understanding", {})
mod_list = fc1.get("solution", {}).get("modification_list", [])
print_agent("L3 FC1", "SolutionPlanner",
    "✅" if "error" not in fc1 else "❌",
    0, "LLM方案生成",
    "压缩特征+需求",
    f"生成{len(mod_list)}项修改方案")
for i, m in enumerate(mod_list[:8]):
    target = m.get("target", "?")
    action = m.get("action", "?")
    print(f"    [{i+1}] {action}: {target}")
if len(mod_list) > 8:
    print(f"    ... 还有{len(mod_list)-8}项")

# L4 FC2
fc2 = layer_outputs.get("fc2_code_generation", {})
fc2_summary = fc2.get("summary", {})
success_mods = fc2_summary.get("successful", 0)
failed_mods = fc2_summary.get("failed", 0)
applied = fc2.get("modifications", [])
print_agent("L4 FC2", "CodeModifier",
    "✅" if "error" not in fc2 else "❌",
    0, "LLM代码生成",
    f"{len(mod_list)}项方案",
    f"成功{success_mods}项, 失败{failed_mods}项")

# 显示生成的文件
generated_files = set()
for m in applied:
    fp = m.get("file_path", "")
    if fp:
        generated_files.add(fp)

if generated_files:
    print(f"\n  📁 生成的文件 ({len(generated_files)}个):")
    for fp in sorted(generated_files):
        p = Path(fp)
        exists = p.exists()
        size = p.stat().st_size if exists else 0
        print(f"    {'✅' if exists else '❌'} {fp} ({size} bytes)" if exists else f"    ❌ {fp} (不存在)")

# L5 FC3
fc3 = layer_outputs.get("fc3_test_generation", {})
fc3_summary = fc3.get("summary", {})
total_tests = fc3_summary.get("total_tests", 0)
print_agent("L5 FC3", "TestCaseGenerator",
    "✅" if "error" not in fc3 else "❌",
    0, "LLM测试生成",
    f"FC2输出({success_mods}项修改)",
    f"生成{total_tests}个测试")

# L6 Output
output = layer_outputs.get("output", {})
doc_path = output.get("document_path", "")
print_agent("L6 Output", "OutputService",
    "✅" if "error" not in output else "❌",
    0, "LLM文档生成",
    "FC1+FC2+FC3输出",
    f"报告: {doc_path}")

# 打印报告预览
if doc_path and Path(doc_path).exists():
    content = Path(doc_path).read_text(encoding="utf-8", errors="replace")
    print(f"\n  📄 报告预览 (前800字符):")
    print(f"  {'─'*60}")
    for line in content[:800].split("\n"):
        print(f"  {line}")
    print(f"  {'─'*60}")

# ============================================================
# 检查生成的项目文件
# ============================================================
print(f"\n{'='*70}")
print(f"  生成的项目文件结构")
print(f"{'='*70}")

project_dir = Path(CODE_REPO)
if project_dir.exists():
    all_files = list(project_dir.rglob("*"))
    all_files = [f for f in all_files if f.is_file() and ".git" not in str(f) and "__pycache__" not in str(f)]
    all_files.sort()

    # 按扩展名分组
    ext_groups = {}
    for f in all_files:
        ext = f.suffix or "其他"
        ext_groups.setdefault(ext, []).append(f)

    print(f"  总文件数: {len(all_files)}")
    for ext, files in sorted(ext_groups.items()):
        print(f"\n  {ext} 文件 ({len(files)}个):")
        for f in files[:10]:
            rel = f.relative_to(project_dir)
            size = f.stat().st_size
            print(f"    {rel} ({size:,} bytes)")
        if len(files) > 10:
            print(f"    ... 还有{len(files)-10}个")

    # 检查关键文件内容
    print(f"\n  {'='*70}")
    print(f"  关键文件内容预览")
    print(f"  {'='*70}")

    key_patterns = ["index.html", "app.js", "style.css", "*.html", "*.js", "*.css"]
    key_files = []
    for p in key_patterns:
        key_files.extend(project_dir.rglob(p))
    key_files = [f for f in key_files if f.is_file() and f.stat().st_size > 50][:6]

    for f in key_files:
        rel = f.relative_to(project_dir)
        content = f.read_text(encoding="utf-8", errors="replace")
        print(f"\n  📄 {rel} ({len(content):,} chars)")
        print(f"  {'─'*50}")
        for line in content[:400].split("\n"):
            print(f"  {line}")
        if len(content) > 400:
            print(f"  ... (共{len(content)}字符)")

# ============================================================
# 总结
# ============================================================
print(f"\n{'='*70}")
print(f"  验证总结")
print(f"{'='*70}")
print(f"  任务: CPA考试刷题网页")
print(f"  总耗时: {total_elapsed/1000:.1f}s")
print(f"  Pipeline状态: {result.get('status', 'unknown')}")
print(f"  生成修改: {success_mods}项成功, {failed_mods}项失败")
print(f"  生成测试: {total_tests}个")
print(f"  生成文件: {len(all_files) if project_dir.exists() else 0}个")
print(f"  报告: {doc_path}")

if not pipeline_error and result.get("status") == "completed":
    print(f"\n  ✅ CPA考试刷题网页生成成功！")
    print(f"  用户可以打开 {CODE_REPO} 中的 HTML 文件查看结果。")
else:
    print(f"\n  ⚠️ 执行遇到问题: {pipeline_error or result.get('status')}")

# 保存报告
report["result"] = {
    "status": result.get("status"),
    "total_elapsed_ms": total_elapsed,
    "modifications": success_mods,
    "tests": total_tests,
    "files_generated": len(all_files) if project_dir.exists() else 0,
    "document_path": doc_path,
}

output_dir = Path("task_output") / "cpa_exam_verify"
output_dir.mkdir(parents=True, exist_ok=True)
rp = output_dir / "cpa_result.json"
rp.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"\n  报告已保存: {rp}")
