"""
全连接层服务单元测试
"""

from app.services.fullconnect.service_fc1 import (
    GlobalUnderstandingService,
    SolutionPlanner
)
from app.services.fullconnect.service_fc2 import (
    CodeGenerationService,
    CodeModifier,
    TrustBasedFilter
)
from app.services.fullconnect.service_fc3 import (
    TestGenerationService,
    TestCaseGenerator,
    CoverageAnalyzer
)


class TestSolutionPlanner:
    """方案规划器测试"""

    def test_generate_overview(self):
        """测试生成概述"""
        planner = SolutionPlanner()

        overview = planner._generate_overview(
            "重构认证模块",
            {"total_files": 5, "total_functions": 20, "total_classes": 3}
        )

        assert "重构认证模块" in overview
        assert "5" in overview
        assert "20" in overview

    def test_is_critical_function(self):
        """测试关键函数判断"""
        planner = SolutionPlanner()

        assert planner._is_critical_function("authenticate_user") is True
        assert planner._is_critical_function("do_something") is False

    def test_generate_modification_list(self):
        """测试生成修改清单"""
        planner = SolutionPlanner()

        mods = planner._generate_modification_list({
            "top_functions": [
                {"name": "authenticate", "file": "auth.py", "line": 10},
                {"name": "helper", "file": "util.py", "line": 5}
            ],
            "top_classes": [
                {"name": "AuthManager", "file": "auth.py", "line": 1}
            ]
        })

        assert len(mods) > 0
        assert any(m["type"] == "function" for m in mods)
        assert any(m["type"] == "class" for m in mods)


class TestGlobalUnderstandingService:
    """全局理解服务测试"""

    def test_create_fc1_output(self, mock_pooling_output, mock_fc1_output):
        """测试创建FC1输出"""
        service = GlobalUnderstandingService()

        output = service.create_fc1_output(
            solution=mock_fc1_output["solution"],
            pooling_output=mock_pooling_output,
            task_id="test-001"
        )

        assert output["task_id"] == "test-001"
        assert output["layer"] == "global_understanding"


class TestCodeModifier:
    """代码修改器测试"""

    def test_generate_modification(self):
        """测试生成修改"""
        modifier = CodeModifier()

        result = modifier.generate_modification(
            {"target": "test_func", "file": "test.py", "action": "modify"},
            "# original code"
        )

        assert "original_code" in result
        assert "modified_code" in result
        assert result["file_path"] == "test.py"

    def test_generate_diff(self):
        """测试生成diff"""
        modifier = CodeModifier()

        diff = modifier._generate_diff("test_func", "modify")

        assert "test_func" in diff
        assert "modify" in diff


class TestTrustBasedFilter:
    """信任度过滤器测试"""

    def test_filter_modifications_high_trust(self):
        """测试高信任度过滤"""
        filter_obj = TrustBasedFilter(threshold_high=0.8, threshold_low=0.6)

        modifications = [
            {"agent_id": "agent_a", "target": "func1"},
            {"agent_id": "agent_b", "target": "func2"}
        ]
        trust_matrix = {"agent_a": 0.9, "agent_b": 0.5}

        filtered = filter_obj.filter_modifications(modifications, trust_matrix)

        assert len(filtered) == 1
        assert filtered[0]["target"] == "func1"


class TestCodeGenerationService:
    """代码生成服务测试"""

    def test_verify_syntax_valid(self):
        """测试语法验证"""
        service = CodeGenerationService()

        result = service.verify_syntax({
            "modified_code": "def test(): return True"
        })

        assert result is True

    def test_verify_syntax_invalid(self):
        """测试无效语法"""
        service = CodeGenerationService()

        result = service.verify_syntax({
            "modified_code": "def test(: return True"  # 语法错误
        })

        assert result is False


class TestTestCaseGenerator:
    """测试用例生成器测试"""

    def test_generate_unit_tests(self):
        """测试生成单元测试"""
        generator = TestCaseGenerator()

        result = generator.generate_unit_tests({
            "target": "test_func",
            "file_path": "test.py"
        })

        assert result["test_type"] == "unit"
        assert "test_code" in result
        assert "import pytest" in result["test_code"]

    def test_generate_integration_tests(self):
        """测试生成集成测试"""
        generator = TestCaseGenerator()

        result = generator.generate_integration_tests({
            "target": "test_func",
            "file_path": "test.py"
        })

        assert result["test_type"] == "integration"


class TestCoverageAnalyzer:
    """覆盖率分析器测试"""

    def test_analyze_coverage(self):
        """测试覆盖率分析"""
        analyzer = CoverageAnalyzer()

        modifications = [
            {"modified_code": "def a(): return 1\ndef b(): return 2"},
            {"modified_code": "def c(): return 3"}
        ]

        result = analyzer.analyze_coverage(modifications)

        assert "total_lines" in result
        assert "covered_lines" in result
        assert "coverage_percent" in result


class TestTestGenerationService:
    """测试生成服务测试"""

    def test_create_fc3_output(self, mock_fc2_output, mock_fc3_output):
        """测试创建FC3输出"""
        service = TestGenerationService()

        output = service.create_fc3_output(
            tests=mock_fc3_output["tests"],
            coverage=mock_fc3_output["coverage"],
            fc2_output=mock_fc2_output,
            task_id="test-001"
        )

        assert output["task_id"] == "test-001"
        assert output["layer"] == "test_generation"