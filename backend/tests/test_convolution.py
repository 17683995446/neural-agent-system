"""
卷积层服务单元测试
"""
import shutil
from pathlib import Path

from app.services.convolution.service import (
    ConvolutionLayerService,
    CodeAnalyzer
)


class TestCodeAnalyzer:
    """代码分析器测试"""

    def test_parse_python_file(self, temp_code_repo):
        """测试解析Python文件"""
        analyzer = CodeAnalyzer()
        file_path = str(Path(temp_code_repo) / "sample_module.py")

        result = analyzer.parse_file(file_path)

        assert "error" not in result
        # language可能是"python"(有tree-sitter)或"unknown"(无tree-sitter)
        assert result["language"] in ("python", "unknown")
        assert result["total_lines"] > 0
        assert len(result["functions"]) > 0

    def test_parse_nonexistent_file(self):
        """测试解析不存在的文件"""
        analyzer = CodeAnalyzer()

        result = analyzer.parse_file("/nonexistent/path/file.py")

        assert "error" in result

    def test_extract_imports(self):
        """测试提取import语句"""
        analyzer = CodeAnalyzer()
        content = '''
import os
import sys
from pathlib import Path
'''
        imports = analyzer._extract_imports(content)

        assert len(imports) == 3
        assert "import os" in imports


class TestConvolutionLayerService:
    """卷积层服务测试"""

    def test_get_code_files(self, temp_code_repo):
        """测试获取代码文件列表"""
        service = ConvolutionLayerService()

        files = service.get_code_files(temp_code_repo)

        assert len(files) > 0
        assert any("sample_module.py" in f or "utils.py" in f for f in files)

    def test_is_excluded(self, temp_code_repo):
        """测试排除目录"""
        service = ConvolutionLayerService()

        # node_modules应该被排除
        assert service._is_excluded(Path("/path/node_modules/file.js")) is True
        # 普通文件不应该被排除
        assert service._is_excluded(Path("/path/normal.py")) is False

    def test_analyze_file(self, temp_code_repo):
        """测试分析单个文件"""
        service = ConvolutionLayerService()
        file_path = str(Path(temp_code_repo) / "sample_module.py")

        result = service.analyze_file(file_path, "test-001")

        assert result["task_id"] == "test-001"
        assert "functions" in result
        assert len(result["functions"]) > 0

    def test_create_convolution_output(self, temp_code_repo):
        """测试创建卷积层输出"""
        service = ConvolutionLayerService()
        file_path = str(Path(temp_code_repo) / "sample_module.py")

        analysis_results = [service.analyze_file(file_path, "test-001")]
        output = service.create_convolution_output(analysis_results, "test-001")

        assert output["task_id"] == "test-001"
        assert output["layer"] == "convolution"
        assert output["total_files"] == 1
        assert len(output["analyzed_files"]) == 1
        assert len(output["failed_files"]) == 0

    def test_process_task(self, temp_code_repo, sample_task_id):
        """测试处理任务"""
        service = ConvolutionLayerService()

        result = service.process_task(sample_task_id, temp_code_repo)

        assert result["task_id"] == sample_task_id
        assert result["layer"] == "convolution"

        # 验证输出文件已创建
        output_file = Path("task_output") / sample_task_id / "convolution" / "analysis_results.json"
        assert output_file.exists()

        # 清理
        shutil.rmtree(Path("task_output") / sample_task_id, ignore_errors=True)