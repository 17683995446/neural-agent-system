"""
交互式迭代循环 — 单进程完整执行
通过环境变量 INTERACTIVE_FEEDBACK 读取反馈
"""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from app.services.pipeline.neural_pipeline import NeuralNetworkPipeline
from app.services.pipeline.iteration_manager import get_iteration_manager


def main():
    task_id = "interactive_task_002"
    user_requirement = "为所有函数添加完整的错误处理、输入验证、日志记录和类型注解，确保代码健壮性达到生产级别"
    max_iteration = 5

    tmpdir = tempfile.mkdtemp(prefix="interactive_repo_")
    src = Path(tmpdir) / "src"
    src.mkdir()

    (src / "main.py").write_text('''import os
import sys

def process_data(data):
    """Process input data"""
    result = []
    for item in data:
        result.append(item * 2)
    return result

def validate_input(data):
    """Validate input"""
    return bool(data)

def transform(data, factor=1):
    """Transform data with factor"""
    return [x * factor for x in data]

def load_file(path):
    """Load file content"""
    with open(path) as f:
        return f.read()

def save_file(path, content):
    """Save content to file"""
    with open(path, 'w') as f:
        f.write(content)

def calculate_stats(numbers):
    """Calculate statistics"""
    total = sum(numbers)
    count = len(numbers)
    average = total / count
    return {"total": total, "count": count, "average": average}
''')

    (src / "models.py").write_text('''from typing import Optional, List, Dict

class DataModel:
    """Data model class"""
    def __init__(self, name: str, value: Optional[int] = None):
        self.name = name
        self.value = value

    def to_dict(self):
        return {"name": self.name, "value": self.value}

    def validate(self):
        return self.name is not None

class ResultModel:
    """Result model class"""
    def __init__(self, success: bool, data=None):
        self.success = success
        self.data = data

    def to_dict(self):
        return {"success": self.success, "data": self.data}

class ConfigModel:
    """Configuration model"""
    def __init__(self, config_dict: Dict):
        self.config = config_dict

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
''')

    (src / "api.py").write_text('''import json

def handle_request(request):
    """Handle API request"""
    method = request.get("method")
    path = request.get("path")
    body = request.get("body", {})

    if method == "GET":
        return {"status": 200, "data": body}
    elif method == "POST":
        return {"status": 201, "data": body}
    else:
        return {"status": 405, "error": "Method not allowed"}

def parse_response(response_str):
    """Parse response string"""
    return json.loads(response_str)

def format_error(code, message):
    """Format error response"""
    return {"status": code, "error": message}
''')

    (src / "database.py").write_text('''from typing import List, Optional

class DatabaseConnection:
    """Database connection manager"""
    def __init__(self, host: str, port: int, name: str):
        self.host = host
        self.port = port
        self.name = name
        self.connected = False

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def query(self, sql: str, params=None):
        if not self.connected:
            raise Exception("Not connected")
        return []

    def execute(self, sql: str, params=None):
        if not self.connected:
            raise Exception("Not connected")
        return True

class Repository:
    """Data repository"""
    def __init__(self, connection: DatabaseConnection):
        self.connection = connection

    def find_by_id(self, id: int):
        return self.connection.query("SELECT * FROM data WHERE id = ?", [id])

    def find_all(self):
        return self.connection.query("SELECT * FROM data")

    def save(self, entity):
        return self.connection.execute("INSERT INTO data VALUES (?)", [entity])

    def delete(self, id: int):
        return self.connection.execute("DELETE FROM data WHERE id = ?", [id])
''')

    pipeline = NeuralNetworkPipeline()

    # 从环境变量读取反馈列表
    feedback_json = os.environ.get("INTERACTIVE_FEEDBACKS", "[]")
    feedbacks = json.loads(feedback_json)

    print("=" * 70)
    print("  交互式迭代循环验证")
    print("=" * 70)
    print(f"  任务ID:   {task_id}")
    print(f"  最大迭代: {max_iteration}")
    print(f"  预设反馈: {len(feedbacks)} 条")
    print(f"  代码仓库: {tmpdir} ({len(list(Path(tmpdir).rglob('*.*')))} 文件)")
    print(f"  需求:     {user_requirement}")
    print("=" * 70)

    # ===== 第1轮 =====
    print(f"\n{'='*70}")
    print(f"  🔄 第1轮: 前向传播")
    print(f"{'='*70}")

    t0 = time.time()
    result = pipeline.start_iterative_pipeline(
        task_id=task_id, user_requirement=user_requirement,
        code_repo_path=tmpdir, max_iteration=max_iteration,
    )
    elapsed = (time.time() - t0) * 1000

    fwd = result.get("forward_result", {})
    layers = fwd.get("layer_outputs", {})
    _print_iteration_result(1, elapsed, layers, result.get("status"))

    # ===== 迭代循环 =====
    for i, fb in enumerate(feedbacks):
        score = fb.get("satisfaction_score", 3)
        stop = fb.get("stop_iteration", False)
        comment = fb.get("comments", "")

        print(f"\n{'='*70}")
        print(f"  💬 用户反馈: satisfaction={score}, stop={stop}, comments='{comment}'")
        print(f"{'='*70}")

        t0 = time.time()
        result = pipeline.process_iteration_feedback(
            task_id=task_id,
            feedback={
                "satisfaction_score": score,
                "stop_iteration": stop,
                "feedback_items": fb.get("feedback_items", []),
                "comments": comment,
            },
        )
        elapsed = (time.time() - t0) * 1000

        iteration = result.get("iteration", "?")
        status = result.get("status", "")
        bw = result.get("backward_result", {})

        print(f"  ⬅️ 反向传播: reward={bw.get('reward', 0):.4f}, {len(bw.get('updated_weights', {}))} 权重更新")

        if status == "completed":
            print(f"\n  🏁 迭代结束 | 第{iteration}轮 | 原因: {result.get('message', '')}")
            break

        if "forward_result" in result:
            fwd2 = result["forward_result"]
            layers2 = fwd2.get("layer_outputs", {})
            _print_iteration_result(iteration, elapsed, layers2, status)
        else:
            print(f"  状态: {status}, 消息: {result.get('message', '')}")

    # ===== 最终汇总 =====
    session = get_iteration_manager().get_session(task_id)
    print(f"\n{'='*70}")
    print(f"  📊 迭代汇总")
    print(f"{'='*70}")
    if session:
        print(f"  总轮数: {session.current_iteration}")
        print(f"  状态:   {session.status}")
        print(f"  各轮详情:")
        for it in session.iterations:
            fwd_ok = "✅" if it.forward_result else "❌"
            bwd_ok = "✅" if it.backward_result else "⏳"
            fb_ok = "✅" if it.user_feedback else "⏳"
            score = it.user_feedback.get("satisfaction_score", "N/A") if it.user_feedback else "N/A"
            print(f"    第{it.iteration}轮: 前向{fwd_ok} 反馈{fb_ok}(score={score}) 反向{bwd_ok}")

    # 验证输出文件
    state_file = Path("task_output") / task_id / "iterations" / "iteration_state.json"
    if state_file.exists():
        final = json.loads(state_file.read_text(encoding="utf-8"))
        print(f"\n  最终状态文件: status={final.get('status')}, iteration={final.get('current_iteration')}")

    shutil.rmtree(tmpdir, ignore_errors=True)


def _print_iteration_result(iteration, elapsed, layers, status):
    conv = layers.get("convolution", {})
    fc1 = layers.get("fc1_global_understanding", {})
    fc2 = layers.get("fc2_code_generation", {})
    fc3 = layers.get("fc3_test_generation", {})
    output = layers.get("output", {})

    print(f"  ✅ 第{iteration}轮完成 | 耗时: {elapsed:.0f}ms | 状态: {status}")
    print(f"     卷积:   {conv.get('total_files', 0)} 文件")
    print(f"     FC1:    {len(fc1.get('solution', {}).get('modification_list', []))} 修改计划")
    print(f"     FC2:    {fc2.get('summary', {}).get('successful', 0)} 成功, {fc2.get('summary', {}).get('failed', 0)} 失败")
    print(f"     FC3:    {fc3.get('summary', {}).get('total_tests', 0)} 测试")
    if output.get("document_path"):
        doc = Path(output["document_path"])
        if doc.exists():
            content = doc.read_text(encoding="utf-8")
            print(f"     报告:   {len(content)} 字符, {len(content.split(chr(10)))} 行")


if __name__ == "__main__":
    main()
