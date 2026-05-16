"""
输出层服务单元测试
"""
from pathlib import Path
import shutil

from app.services.output.service import (
    OutputLayerService,
    DocumentTemplate
)


class TestDocumentTemplate:
    """文档模板测试"""

    def test_generate_task_report(self, mock_fc1_output, mock_fc2_output, mock_fc3_output):
        """测试生成任务报告"""
        template = DocumentTemplate()

        report = template.generate_task_report(
            task_id="test-001",
            user_requirement="重构认证模块",
            fc1_output=mock_fc1_output,
            fc2_output=mock_fc2_output,
            fc3_output=mock_fc3_output,
            execution_time_ms=1000.0
        )

        assert "代码修改任务报告" in report
        assert "test-001" in report
        assert "重构认证模块" in report
        assert "test_module.py" in report or "modifications" in report.lower() or "test" in report.lower()

    def test_generate_simple_summary(self, mock_fc2_output, mock_fc3_output):
        """测试生成简化摘要"""
        template = DocumentTemplate()

        summary = template.generate_simple_summary(
            task_id="test-001",
            user_requirement="测试需求",
            fc2_output=mock_fc2_output,
            fc3_output=mock_fc3_output
        )

        assert "test-001" in summary


class TestOutputLayerService:
    """输出层服务测试"""

    def test_generate_document(self, mock_fc1_output, mock_fc2_output, mock_fc3_output):
        """测试生成文档"""
        service = OutputLayerService()

        doc = service.generate_document(
            task_id="test-001",
            user_requirement="重构认证模块",
            fc1_output=mock_fc1_output,
            fc2_output=mock_fc2_output,
            fc3_output=mock_fc3_output,
            execution_time_ms=500.0
        )

        assert "代码修改任务报告" in doc
        assert len(doc) > 0

    def test_save_document(self, sample_task_id):
        """测试保存文档"""
        service = OutputLayerService()

        content = "# Test Document\nThis is a test."
        doc_path = service.save_document(sample_task_id, content)

        assert Path(doc_path).exists()
        assert content in Path(doc_path).read_text()

        # 清理
        shutil.rmtree(Path("task_output") / sample_task_id, ignore_errors=True)

    def test_create_output_metadata(self, mock_fc2_output, mock_fc3_output):
        """测试创建输出元数据"""
        service = OutputLayerService()

        metadata = service.create_output_metadata(
            task_id="test-001",
            doc_path="/path/to/doc.md",
            fc2_output=mock_fc2_output,
            fc3_output=mock_fc3_output
        )

        assert metadata["task_id"] == "test-001"
        assert metadata["layer"] == "output"
        assert "statistics" in metadata
        assert metadata["statistics"]["total_modifications"] == 1

    def test_process_task(self, mock_fc1_output, mock_fc2_output, mock_fc3_output, sample_task_id):
        """测试处理任务"""
        service = OutputLayerService()

        result = service.process_task(
            task_id=sample_task_id,
            user_requirement="测试需求",
            fc1_output=mock_fc1_output,
            fc2_output=mock_fc2_output,
            fc3_output=mock_fc3_output,
            execution_time_ms=1000.0
        )

        assert result["task_id"] == sample_task_id
        assert result["layer"] == "output"
        assert "document_path" in result

        # 清理
        shutil.rmtree(Path("task_output") / sample_task_id, ignore_errors=True)