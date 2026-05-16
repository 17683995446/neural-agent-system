"""
测试配置和共享fixtures
"""
import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_code_repo():
    """创建临时代码仓库用于测试"""
    temp_dir = tempfile.mkdtemp()

    # 创建测试Python文件
    test_files = {
        "sample_module.py": '''
def hello_world():
    """Test function"""
    return "Hello, World!"

def add_numbers(a, b):
    """Add two numbers"""
    return a + b

class Calculator:
    """Simple calculator class"""
    def add(self, a, b):
        return a + b
''',
        "utils.py": '''
import os

def get_config():
    """Get configuration"""
    return {"debug": True}

def parse_args():
    """Parse arguments"""
    return {}
''',
        "models.py": '''
from dataclasses import dataclass

@dataclass
class User:
    name: str
    email: str
'''
    }

    for filename, content in test_files.items():
        (Path(temp_dir) / filename).write_text(content, encoding="utf-8")

    yield temp_dir

    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_task_id():
    """样例任务ID"""
    return "test-task-001"


@pytest.fixture
def sample_user_requirement():
    """样例用户需求"""
    return "重构用户认证模块，添加JWT支持"


@pytest.fixture
def mock_convolution_output():
    """模拟卷积层输出"""
    return {
        "task_id": "test-task-001",
        "layer": "convolution",
        "analyzed_files": [
            {
                "file_path": "test_module.py",
                "language": "python",
                "total_lines": 20,
                "functions": [
                    {"name": "hello_world", "start_line": 2, "end_line": 5},
                    {"name": "add_numbers", "start_line": 7, "end_line": 10}
                ],
                "classes": [
                    {"name": "Calculator", "start_line": 12, "end_line": 16}
                ],
                "imports": ["os"]
            }
        ],
        "failed_files": [],
        "summary": {
            "total_functions": 2,
            "total_classes": 1
        }
    }


@pytest.fixture
def mock_pooling_output(mock_convolution_output):
    """模拟池化层输出"""
    return {
        "task_id": "test-task-001",
        "layer": "pooling",
        "user_requirement": "重构用户认证模块，添加JWT支持",
        "compressed_features": mock_convolution_output["analyzed_files"],
        "global_features": {
            "total_files": 1,
            "total_functions": 2,
            "total_classes": 1,
            "unique_imports": ["os"],
            "top_functions": [
                {"name": "hello_world", "file": "test_module.py", "line": 2}
            ],
            "top_classes": [
                {"name": "Calculator", "file": "test_module.py", "line": 12}
            ]
        },
        "total_files_processed": 1
    }


@pytest.fixture
def mock_fc1_output():
    """模拟FC1输出"""
    return {
        "task_id": "test-task-001",
        "layer": "global_understanding",
        "solution": {
            "overview": "根据用户需求，分析得到代码工程包含1个文件、2个函数、1个类",
            "modification_list": [
                {
                    "type": "function",
                    "target": "hello_world",
                    "file": "test_module.py",
                    "action": "analyze_and_modify",
                    "priority": "medium"
                }
            ],
            "execution_order": ["function:hello_world"],
            "risk_points": [],
            "architecture": {
                "main_components": ["Calculator"],
                "main_functions": ["hello_world", "add_numbers"],
                "entry_points": ["hello_world"]
            }
        }
    }


@pytest.fixture
def mock_fc2_output():
    """模拟FC2输出"""
    return {
        "task_id": "test-task-001",
        "layer": "code_generation",
        "summary": {
            "total_modifications": 1,
            "successful": 1,
            "failed": 0
        },
        "modifications": [
            {
                "target": "hello_world",
                "file_path": "test_module.py",
                "status": "success",
                "modified_code": "# Modified hello_world",
                "syntax_valid": True
            }
        ]
    }


@pytest.fixture
def mock_fc3_output():
    """模拟FC3输出"""
    return {
        "task_id": "test-task-001",
        "layer": "test_generation",
        "summary": {
            "total_tests": 2,
            "unit_tests": 1,
            "integration_tests": 1
        },
        "tests": [
            {
                "test_type": "unit",
                "target": "hello_world",
                "status": "generated",
                "test_code": "import pytest\n..."
            }
        ],
        "coverage": {
            "total_lines": 10,
            "covered_lines": 7,
            "coverage_percent": 70.0
        }
    }