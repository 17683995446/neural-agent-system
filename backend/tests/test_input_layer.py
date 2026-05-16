"""
输入层服务单元测试
"""
import pytest

from app.services.input_layer.service import InputLayerService
from app.models.schemas import TaskInput


class TestInputLayerService:
    """输入层服务测试"""

    def test_validate_task_input_valid(self):
        """测试有效任务输入"""
        service = InputLayerService()

        task_input = TaskInput(
            task_id="test-001",
            user_requirement="测试需求",
            local_code_path="/tmp/test"
        )

        # 应该验证通过（不抛异常）
        result = service.validate_task_input(task_input)
        assert result is True

    def test_validate_task_input_empty_requirement(self):
        """测试空需求验证失败"""
        service = InputLayerService()

        task_input = TaskInput(
            task_id="test-001",
            user_requirement="",
            local_code_path="/tmp/test"
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            service.validate_task_input(task_input)

        assert exc_info.value.status_code == 400

    def test_validate_task_input_no_code_source(self):
        """测试没有代码源的验证"""
        service = InputLayerService()

        task_input = TaskInput(
            task_id="test-001",
            user_requirement="测试需求"
            # 既没有code_repo_url也没有local_code_path
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            service.validate_task_input(task_input)

        assert exc_info.value.status_code == 400

    def test_validate_task_input_both_sources(self):
        """测试同时提供两个代码源的验证"""
        service = InputLayerService()

        task_input = TaskInput(
            task_id="test-001",
            user_requirement="测试需求",
            code_repo_url="https://github.com/test/repo",
            local_code_path="/tmp/test"
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            service.validate_task_input(task_input)

        assert exc_info.value.status_code == 400

    def test_create_task_context(self, temp_code_repo):
        """测试创建任务上下文"""
        service = InputLayerService()

        task_input = TaskInput(
            task_id="test-001",
            user_requirement="测试需求",
            local_code_path=temp_code_repo,
            max_iteration=5,
            learning_rate=0.1
        )

        context = service.create_task_context(task_input, temp_code_repo)

        assert context.task_id == "test-001"
        assert context.user_requirement == "测试需求"
        assert context.code_repo_path == temp_code_repo
        assert context.max_iteration == 5
        assert context.learning_rate == 0.1
        assert context.current_iteration == 0

    def test_create_task_output_dir(self, sample_task_id):
        """测试创建任务输出目录"""
        service = InputLayerService()

        output_dir = service.create_task_output_dir(sample_task_id)

        assert output_dir.exists()
        expected_subdirs = [
            "convolution", "pooling", "global_understanding",
            "code_generation", "test_generation", "output"
        ]
        for subdir in expected_subdirs:
            assert (output_dir / subdir).exists()

        # 清理
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)