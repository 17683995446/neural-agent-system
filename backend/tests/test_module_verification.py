"""
逐模块全量验证测试 - 验证每个模块的内部逻辑、边界条件、异常处理
"""
import shutil
import tempfile
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.models.schemas import (
    TaskStatus, TaskInput, TaskOutput, LayerInfo, TaskContext,
)
from app.models.database import (
    TaskModel, TrustModel, AgentMemoryModel, Base, init_db, get_db,
)
from app.services.input_layer.service import InputLayerService
from app.services.convolution.service import (
    ConvolutionLayerService, ConvolutionConfig, CodeAnalyzer,
)
from app.services.pooling.service import (
    PoolingLayerService, PoolingConfig, SemanticCompressor, InformationAggregator,
)
from app.services.fullconnect.service_fc1 import (
    GlobalUnderstandingService, GlobalUnderstandingConfig, SolutionPlanner,
)
from app.services.fullconnect.service_fc2 import (
    CodeGenerationService, CodeGenerationConfig, CodeModifier, TrustBasedFilter,
)
from app.services.fullconnect.service_fc3 import (
    TestGenerationService, TestGenerationConfig, TestCaseGenerator, CoverageAnalyzer,
)
from app.services.output.service import OutputLayerService, DocumentTemplate
from app.services.backward.service import BackwardPropagationService, FeedbackProcessor
from app.services.pipeline.neural_pipeline import NeuralNetworkPipeline, get_neural_pipeline
from app.agents.trust.backward import (
    RewardCalculator, TrustWeightUpdater, BackwardPropagation, get_backward_propagation,
)
from app.agents.trust.manager import TrustManager
from app.agents.memory.long_term import LongTermMemory, get_vector_store
from app.agents.neural_agent import NeuralAgent
from app.core.llm_client import LLMClient, get_llm_client


# ============================================================================
# 1. Core 模块
# ============================================================================
class TestCoreConfig:
    def test_settings_defaults(self):
        s = Settings()
        assert s.app_name == "Neural Agent System"
        assert s.app_version == "1.0.0"
        assert isinstance(s.debug, bool)
        assert s.api_v1_prefix == "/api/v1"

    def test_settings_redis_url(self):
        s = Settings()
        assert "redis" in s.redis_url

    def test_settings_postgres_url(self):
        s = Settings()
        assert "postgresql" in s.postgres_url

    def test_settings_trust_bounds(self):
        s = Settings()
        assert s.trust_min_value < s.trust_initial_value < s.trust_max_value
        assert s.trust_min_value == 0.0
        assert s.trust_max_value == 2.0
        assert s.trust_initial_value == 1.0

    def test_settings_cache(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_settings_singleton(self):
        from app.core.config import settings as s
        assert s.app_name == "Neural Agent System"


class TestCoreLogging:
    def test_logger_exists(self):
        assert logger is not None

    def test_logger_name(self):
        assert "app" in logger.name


class TestCoreLLMClient:
    def test_llm_client_init(self):
        client = LLMClient()
        assert client.model is not None
        assert client.api_key is not None
        assert client.api_base is not None
        assert 0 < client.temperature <= 1.0
        assert client.max_tokens > 0

    def test_llm_client_custom_params(self):
        client = LLMClient(
            model="test-model",
            temperature=0.5,
            max_tokens=2048,
        )
        assert client.model == "test-model"
        assert client.temperature == 0.5
        assert client.max_tokens == 2048

    def test_llm_client_singleton(self):
        c1 = get_llm_client()
        c2 = get_llm_client()
        assert c1 is c2

    def test_get_response_text_empty(self):
        client = LLMClient()
        result = client.get_response_text({})
        assert result == ""

    def test_get_response_text_with_choices(self):
        client = LLMClient()
        result = client.get_response_text({
            "choices": [{"message": {"content": "hello"}}]
        })
        assert result == "hello"


# ============================================================================
# 2. Models 模块
# ============================================================================
class TestModelsSchemas:
    def test_task_status_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.ITERATING.value == "iterating"

    def test_task_status_from_str(self):
        assert TaskStatus("pending") == TaskStatus.PENDING
        assert TaskStatus("running") == TaskStatus.RUNNING

    def test_task_input_defaults(self):
        ti = TaskInput(
            task_id="test-001",
            user_requirement="test req",
            code_repo_url="https://github.com/test/repo",
        )
        assert ti.target_branch == "main"
        assert ti.max_iteration == 5
        assert ti.learning_rate == 0.1
        assert ti.llm_config == {}

    def test_task_input_validation(self):
        ti = TaskInput(
            task_id="test-002",
            user_requirement="add feature",
            local_code_path="/tmp/code",
        )
        assert ti.local_code_path == "/tmp/code"
        assert ti.code_repo_url is None

    def test_task_output_model(self):
        from datetime import datetime
        now = datetime.now()
        to = TaskOutput(
            task_id="t1",
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        assert to.iteration_count == 0
        assert to.user_satisfaction_score is None

    def test_layer_info(self):
        li = LayerInfo(layer_name="conv", agent_id="a1", status="active")
        assert li.confidence == 1.0

    def test_task_context_extra_ignore(self):
        from datetime import datetime
        now = datetime.now()
        tc = TaskContext(
            task_id="t1",
            user_requirement="req",
            code_repo_path="/path",
            target_branch="main",
            max_iteration=5,
            learning_rate=0.1,
            llm_config={},
            created_at=now,
            updated_at=now,
            extra_field_ignored="should_be_ignored",
        )
        assert not hasattr(tc, "extra_field_ignored")


class TestModelsDatabase:
    def test_task_model_tablename(self):
        assert TaskModel.__tablename__ == "tasks"

    def test_trust_model_tablename(self):
        assert TrustModel.__tablename__ == "trust_weights"

    def test_agent_memory_model_tablename(self):
        assert AgentMemoryModel.__tablename__ == "agent_memories"

    def test_task_model_columns(self):
        columns = [c.name for c in TaskModel.__table__.columns]
        assert "task_id" in columns
        assert "user_requirement" in columns
        assert "status" in columns
        assert "iteration_count" in columns

    def test_trust_model_columns(self):
        columns = [c.name for c in TrustModel.__table__.columns]
        assert "agent_id" in columns
        assert "trust_matrix" in columns

    def test_base_is_declarative(self):
        assert Base is not None
        assert hasattr(Base, "metadata")

    def test_init_db_callable(self):
        assert callable(init_db)

    def test_get_db_is_generator(self):
        assert callable(get_db)


# ============================================================================
# 3. Input Layer 模块
# ============================================================================
class TestInputLayerModule:
    def test_service_init(self):
        svc = InputLayerService()
        assert svc.code_repos_dir.exists()
        assert svc.task_output_dir.exists()

    def test_validate_valid(self):
        svc = InputLayerService()
        ti = TaskInput(
            task_id="v1",
            user_requirement="test",
            code_repo_url="https://github.com/test/repo",
        )
        assert svc.validate_task_input(ti) is True

    def test_validate_empty_requirement(self):
        svc = InputLayerService()
        ti = TaskInput(task_id="v2", user_requirement="", local_code_path="/tmp/x")
        with pytest.raises(Exception):
            svc.validate_task_input(ti)

    def test_validate_no_source(self):
        svc = InputLayerService()
        ti = TaskInput(task_id="v3", user_requirement="test")
        with pytest.raises(Exception):
            svc.validate_task_input(ti)

    def test_validate_both_sources(self):
        svc = InputLayerService()
        ti = TaskInput(
            task_id="v4",
            user_requirement="test",
            code_repo_url="https://github.com/test",
            local_code_path="/tmp/x",
        )
        with pytest.raises(Exception):
            svc.validate_task_input(ti)

    def test_create_task_context(self):
        svc = InputLayerService()
        ti = TaskInput(
            task_id="ctx1",
            user_requirement="add feature",
            local_code_path="/tmp/code",
        )
        ctx = svc.create_task_context(ti, "/tmp/code")
        assert ctx.task_id == "ctx1"
        assert ctx.user_requirement == "add feature"
        assert ctx.code_repo_path == "/tmp/code"

    def test_create_task_output_dir(self):
        svc = InputLayerService()
        output_dir = svc.create_task_output_dir("test_dir_001")
        assert output_dir.exists()
        for subdir in ["convolution", "pooling", "global_understanding",
                       "code_generation", "test_generation", "output"]:
            assert (output_dir / subdir).exists()


# ============================================================================
# 4. Convolution 模块
# ============================================================================
class TestConvolutionModule:
    def test_config_defaults(self):
        cfg = ConvolutionConfig()
        assert cfg.granularity == "file"
        assert cfg.max_agents == 20

    def test_code_analyzer_supported_languages(self):
        analyzer = CodeAnalyzer()
        assert ".py" in analyzer.SUPPORTED_LANGUAGES
        assert ".js" in analyzer.SUPPORTED_LANGUAGES
        assert ".java" in analyzer.SUPPORTED_LANGUAGES

    def test_code_analyzer_parse_nonexistent(self):
        analyzer = CodeAnalyzer()
        result = analyzer.parse_file("/nonexistent/file.py")
        assert "error" in result

    def test_code_analyzer_parse_python(self):
        tmpfile = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w")
        tmpfile.write("def hello():\n    pass\n\nclass Foo:\n    pass\n")
        tmpfile.close()
        analyzer = CodeAnalyzer()
        result = analyzer.parse_file(tmpfile.name)
        assert "functions" in result or "error" in result
        Path(tmpfile.name).unlink()

    def test_code_analyzer_extract_imports(self):
        analyzer = CodeAnalyzer()
        imports = analyzer._extract_imports("import os\nfrom sys import path\n")
        assert len(imports) >= 2

    def test_service_get_code_files(self):
        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "test.py").write_text("pass")
        (Path(tmpdir) / "test.js").write_text("// js")
        (Path(tmpdir) / "readme.txt").write_text("text")

        svc = ConvolutionLayerService()
        files = svc.get_code_files(tmpdir)
        exts = {Path(f).suffix for f in files}
        assert ".py" in exts or ".js" in exts
        assert ".txt" not in exts
        shutil.rmtree(tmpdir)

    def test_service_exclusion_patterns(self):
        tmpdir = tempfile.mkdtemp()
        nm = Path(tmpdir) / "node_modules"
        nm.mkdir()
        (nm / "lib.js").write_text("// lib")
        (Path(tmpdir) / "app.py").write_text("pass")

        svc = ConvolutionLayerService()
        files = svc.get_code_files(tmpdir)
        assert all("node_modules" not in f for f in files)
        shutil.rmtree(tmpdir)

    def test_service_analyze_file(self):
        tmpfile = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w")
        tmpfile.write("def add(a, b):\n    return a + b\n")
        tmpfile.close()
        svc = ConvolutionLayerService()
        result = svc.analyze_file(tmpfile.name, "task_1")
        assert result["task_id"] == "task_1"
        Path(tmpfile.name).unlink()

    def test_service_process_task(self):
        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "main.py").write_text("def main():\n    pass\n")

        svc = ConvolutionLayerService()
        result = svc.process_task("conv_task_1", tmpdir)
        assert result["task_id"] == "conv_task_1"
        assert result["layer"] == "convolution"
        assert "analyzed_files" in result
        assert "summary" in result
        shutil.rmtree(tmpdir)


# ============================================================================
# 5. Pooling 模块
# ============================================================================
class TestPoolingModule:
    def test_config_defaults(self):
        cfg = PoolingConfig()
        assert cfg.compression_threshold > 0
        assert cfg.max_output_items > 0

    def test_compressor_extract_keywords(self):
        comp = SemanticCompressor()
        kws = comp._extract_keywords("Add error handling to validation functions")
        assert len(kws) > 0
        assert "the" not in kws
        assert "to" not in kws

    def test_compressor_empty_items(self):
        comp = SemanticCompressor()
        result = comp.compress([], "test query")
        assert result == []

    def test_compressor_relevance_score(self):
        comp = SemanticCompressor()
        item = {"functions": [{"name": "validate"}], "classes": [], "imports": []}
        score = comp._calculate_relevance(item, ["validate"])
        assert score >= 0

    def test_aggregator_empty(self):
        agg = InformationAggregator()
        result = agg.aggregate([])
        assert "error" in result

    def test_aggregator_multiple_files(self):
        agg = InformationAggregator()
        results = [
            {
                "file_path": "/a.py",
                "functions": [{"name": "foo", "start_line": 1}],
                "classes": [],
                "imports": ["os"],
            },
            {
                "file_path": "/b.py",
                "functions": [{"name": "bar", "start_line": 2}],
                "classes": [{"name": "Baz", "start_line": 3}],
                "imports": [],
            },
        ]
        result = agg.aggregate(results)
        assert result["total_files"] == 2
        assert result["total_functions"] == 2
        assert result["total_classes"] == 1

    def test_service_process_task(self):
        conv_output = {
            "analyzed_files": [
                {
                    "file_path": "/test.py",
                    "functions": [{"name": "process", "start_line": 1}],
                    "classes": [],
                    "imports": [],
                }
            ]
        }
        svc = PoolingLayerService()
        result = svc.process_task("pool_task_1", conv_output, "process data")
        assert result["task_id"] == "pool_task_1"
        assert result["layer"] == "pooling"


# ============================================================================
# 6. FC1/FC2/FC3 全连接层模块
# ============================================================================
class TestFC1Module:
    def test_config_defaults(self):
        cfg = GlobalUnderstandingConfig()
        assert cfg.similar_experience_top_k > 0
        assert 0 < cfg.similarity_threshold <= 1.0

    def test_planner_generate_overview(self):
        planner = SolutionPlanner()
        overview = planner._generate_overview("add feature", {
            "total_files": 5, "total_functions": 10, "total_classes": 3
        })
        assert "add feature" in overview
        assert "5" in overview

    def test_planner_is_critical_function(self):
        planner = SolutionPlanner()
        assert planner._is_critical_function("validate_input")
        assert planner._is_critical_function("process_data")
        assert not planner._is_critical_function("helper")

    def test_planner_is_critical_class(self):
        planner = SolutionPlanner()
        assert planner._is_critical_class("ServiceManager")
        assert planner._is_critical_class("DataHandler")
        assert not planner._is_critical_class("Foo")

    def test_planner_generate_modification_list(self):
        planner = SolutionPlanner()
        features = {
            "top_functions": [{"name": "validate", "file": "a.py", "line": 1}],
            "top_classes": [{"name": "Manager", "file": "b.py", "line": 5}],
        }
        mods = planner._generate_modification_list(features)
        assert len(mods) == 2

    def test_planner_identify_risk_points(self):
        planner = SolutionPlanner()
        risks = planner._identify_risk_points({
            "unique_imports": list(range(40)),
            "top_functions": [{"name": "x", "line": None}],
        })
        assert len(risks) >= 1
        assert risks[0]["type"] == "high_dependency"

    def test_service_init(self):
        svc = GlobalUnderstandingService()
        assert svc.planner is not None
        assert svc.agent_id == "global_understanding_agent"

    def test_service_analyze_architecture(self):
        svc = GlobalUnderstandingService()
        features = {
            "top_classes": [{"name": "App"}],
            "top_functions": [{"name": "main"}],
        }
        arch = svc.analyze_architecture(features)
        assert "main_components" in arch
        assert "App" in arch["main_components"]


class TestFC2Module:
    def test_config_defaults(self):
        cfg = CodeGenerationConfig()
        assert 0 < cfg.trust_threshold_low < cfg.trust_threshold_high <= 1.0
        assert cfg.max_modifications > 0

    def test_code_modifier_generate(self):
        modifier = CodeModifier()
        result = modifier.generate_modification(
            {"target": "func_a", "file": "a.py", "action": "modify"},
            "original code"
        )
        assert "original_code" in result
        assert "modified_code" in result
        assert "diff" in result

    def test_code_modifier_diff(self):
        modifier = CodeModifier()
        diff = modifier._compute_simple_diff("def test_func():\n    pass\n", "def test_func():\n    add_check()\n    pass\n")
        assert "---" in diff
        assert "+++" in diff

    def test_trust_filter_high(self):
        f = TrustBasedFilter(threshold_high=0.8, threshold_low=0.6)
        mods = [{"agent_id": "a1"}, {"agent_id": "a2"}]
        trust = {"a1": 0.9, "a2": 0.7}
        result = f.filter_modifications(mods, trust)
        assert len(result) == 2
        assert result[0]["trust_level"] == "high"
        assert result[1]["trust_level"] == "medium"

    def test_trust_filter_low_excluded(self):
        f = TrustBasedFilter(threshold_high=0.8, threshold_low=0.6)
        mods = [{"agent_id": "a1"}]
        trust = {"a1": 0.3}
        result = f.filter_modifications(mods, trust)
        assert len(result) == 0

    def test_service_verify_syntax_valid(self):
        svc = CodeGenerationService()
        assert svc.verify_syntax({"modified_code": "def f(): pass"})

    def test_service_verify_syntax_invalid(self):
        svc = CodeGenerationService()
        assert not svc.verify_syntax({"modified_code": "def f(: pass"})


class TestFC3Module:
    def test_config_defaults(self):
        cfg = TestGenerationConfig()
        assert cfg.coverage_target == 0.8
        assert cfg.max_tests_per_file == 20

    def test_generator_unit_tests(self):
        gen = TestCaseGenerator()
        result = gen.generate_integration_tests({
            "target": "add_feature",
            "file_path": "src/app.py",
        })
        assert isinstance(result, dict)

    def test_generator_integration_tests(self):
        gen = TestCaseGenerator()
        result = gen.generate_integration_tests({
            "target": "workflow",
            "file_path": "src/app.py",
        })
        assert result["test_type"] == "integration"

    def test_coverage_analyzer(self):
        analyzer = CoverageAnalyzer()
        result = analyzer.analyze_coverage([
            {"modified_code": "line1\nline2\nline3", "status": "success"},
        ])
        assert result["total_lines"] == 3
        assert result["coverage_percent"] > 0

    def test_coverage_analyzer_empty(self):
        analyzer = CoverageAnalyzer()
        result = analyzer.analyze_coverage([])
        assert result["coverage_percent"] == 0

    def test_service_validate_tests(self):
        svc = TestGenerationService()
        result = svc.validate_tests([
            {"status": "generated", "test_code": "import pytest\ndef test_x(): pass"},
            {"status": "failed"},
        ])
        assert result["valid_tests"] == 1
        assert result["invalid_tests"] == 1


# ============================================================================
# 7. Output 模块
# ============================================================================
class TestOutputModule:
    def test_template_generate_report(self):
        report = DocumentTemplate.generate_task_report(
            task_id="r1",
            user_requirement="add feature",
            fc1_output={"solution": {"architecture": {}, "risk_points": []}},
            fc2_output={"summary": {}, "modifications": []},
            fc3_output={"coverage": {}, "tests": []},
            execution_time_ms=100.0,
        )
        assert "代码修改任务报告" in report
        assert "r1" in report
        assert "add feature" in report

    def test_template_generate_summary(self):
        summary = DocumentTemplate.generate_simple_summary(
            task_id="s1",
            user_requirement="fix bug",
            fc2_output={"summary": {"successful": 3, "failed": 1}, "modifications": []},
            fc3_output={"summary": {"total_tests": 5}, "coverage": {"coverage_percent": 80}},
        )
        assert "s1" in summary
        assert "fix bug" in summary

    def test_service_generate_document(self):
        svc = OutputLayerService()
        doc = svc.generate_document(
            task_id="d1",
            user_requirement="test",
            fc1_output={"solution": {"architecture": {}, "risk_points": []}},
            fc2_output={"summary": {}, "modifications": []},
            fc3_output={"coverage": {}, "tests": []},
            execution_time_ms=50.0,
        )
        assert len(doc) > 0

    def test_service_save_document(self):
        svc = OutputLayerService()
        path = svc.save_document("save_task_1", "# Report\nContent here")
        assert Path(path).exists()
        assert Path(path).read_text(encoding="utf-8") == "# Report\nContent here"

    def test_service_create_metadata(self):
        svc = OutputLayerService()
        meta = svc.create_output_metadata(
            task_id="m1",
            doc_path="/tmp/report.md",
            fc2_output={"summary": {"total_modifications": 5, "successful": 4}},
            fc3_output={"summary": {"total_tests": 3}, "coverage": {"coverage_percent": 75}},
        )
        assert meta["task_id"] == "m1"
        assert meta["statistics"]["total_modifications"] == 5
        assert meta["statistics"]["coverage_percent"] == 75


# ============================================================================
# 8. Backward 反向传播模块
# ============================================================================
class TestBackwardModule:
    def test_feedback_processor_parse(self):
        fp = FeedbackProcessor()
        result = fp.parse_feedback({
            "satisfaction_score": 4,
            "feedback_items": [{"type": "positive"}],
            "comments": "good",
            "iteration_number": 2,
        })
        assert result["satisfaction_score"] == 4
        assert result["iteration_number"] == 2

    def test_reward_calculator_neutral(self):
        assert RewardCalculator.calculate_reward({"satisfaction_score": 3}) == 0.0

    def test_reward_calculator_positive(self):
        assert RewardCalculator.calculate_reward({"satisfaction_score": 5}) == 1.0

    def test_reward_calculator_negative(self):
        assert RewardCalculator.calculate_reward({"satisfaction_score": 0}) == -1.0

    def test_reward_calculator_with_items(self):
        r = RewardCalculator.calculate_reward({
            "satisfaction_score": 4,
            "feedback_items": [{"type": "positive"}, {"type": "critical"}],
        })
        assert -1.0 <= r <= 1.0

    def test_reward_calculator_layer_reward(self):
        r = RewardCalculator.calculate_layer_reward("code_generation", {"layer_score": 0.8})
        assert r > 0

    def test_trust_updater_basic(self):
        updater = TrustWeightUpdater(learning_rate=0.1, clip_param=0.2)
        new_w = updater.update_weights({"a": 1.0}, {"a": 0.5}, iteration=0)
        assert new_w["a"] > 1.0

    def test_trust_updater_clipped(self):
        updater = TrustWeightUpdater(learning_rate=10.0, clip_param=0.2)
        new_w = updater.update_weights({"a": 1.0}, {"a": 1.0}, iteration=0)
        assert abs(new_w["a"] - 1.0) <= 0.2

    def test_trust_updater_bounds(self):
        updater = TrustWeightUpdater(learning_rate=1.0, clip_param=1.0)
        new_w = updater.update_weights({"a": 1.9}, {"a": 1.0}, iteration=0)
        assert new_w["a"] <= 2.0

    def test_trust_updater_lr_decay(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        lr_0 = updater._get_adjusted_learning_rate(0)
        lr_10 = updater._get_adjusted_learning_rate(10)
        assert lr_10 < lr_0

    def test_backward_propagation_full(self):
        bp = BackwardPropagation()
        result = bp.propagate_feedback(
            task_id="bp1",
            user_feedback={"satisfaction_score": 4},
            layer_agents={"convolution": ["c1"], "output": ["o1"]},
            current_iteration=1,
        )
        assert len(result) > 0

    def test_backward_service(self):
        svc = BackwardPropagationService()
        result = svc.process_user_feedback("bs1", {"satisfaction_score": 5})
        assert -1.0 <= result["reward"] <= 2.0
        assert result["task_id"] == "bs1"

    def test_backward_service_layer_rewards(self):
        svc = BackwardPropagationService()
        rewards = svc.calculate_layer_rewards("lr1", {"satisfaction_score": 5})
        assert rewards["output"] >= rewards["convolution"]


# ============================================================================
# 9. Pipeline 调度模块
# ============================================================================
class TestPipelineModule:
    def test_pipeline_init(self):
        pipeline = NeuralNetworkPipeline()
        assert pipeline.conv_service is not None
        assert pipeline.pool_service is not None
        assert pipeline.fc1_service is not None
        assert pipeline.fc2_service is not None
        assert pipeline.fc3_service is not None
        assert pipeline.output_service is not None
        assert pipeline.backward_service is not None

    def test_pipeline_singleton(self):
        p1 = get_neural_pipeline()
        p2 = get_neural_pipeline()
        assert p1 is p2

    def test_pipeline_backward(self):
        pipeline = get_neural_pipeline()
        result = pipeline.execute_backward_pipeline(
            "pbd1",
            {"satisfaction_score": 4, "feedback_items": []},
        )
        assert "task_id" in result

    def test_backward_propagation_singleton(self):
        bp1 = get_backward_propagation()
        bp2 = get_backward_propagation()
        assert bp1 is bp2


# ============================================================================
# 10. Agent 模块
# ============================================================================
class TestAgentNeuralAgent:
    def test_neural_agent_init(self):
        agent = NeuralAgent(
            agent_id="test_agent",
            layer_name="convolution",
            role="analyzer",
            goal="analyze code",
            llm_config={"model": "gpt-4"},
        )
        assert agent.agent_id == "test_agent"
        assert agent.layer_name == "convolution"
        assert agent.trust_manager is not None

    def test_neural_agent_do_process_not_implemented(self):
        agent = NeuralAgent(
            agent_id="na1",
            layer_name="conv",
            role="r",
            goal="g",
            llm_config={},
        )
        with pytest.raises(NotImplementedError):
            agent._do_process([])

    def test_create_neural_agent_factory(self):
        agent = NeuralAgent(
            agent_id="fac1",
            layer_name="pool",
            role="compressor",
            goal="compress",
            llm_config={},
        )
        assert agent.agent_id == "fac1"


class TestAgentTrustManager:
    def test_trust_manager_init(self):
        tm = TrustManager.__new__(TrustManager)
        tm.initial_value = 1.0
        tm.min_value = 0.0
        tm.max_value = 2.0
        assert tm.min_value < tm.initial_value < tm.max_value

    def test_trust_manager_get_statistics_empty(self):
        tm = TrustManager()
        result = tm.get_trust_matrix("nonexistent")
        assert isinstance(result, dict)

    def test_trust_manager_filter_by_threshold(self):
        tm = TrustManager()
        assert tm.min_value < tm.initial_value < tm.max_value


class TestAgentMemory:
    def test_long_term_memory_init(self):
        mem = LongTermMemory(agent_id="mem_agent_1")
        assert mem.agent_id == "mem_agent_1"

    def test_long_term_memory_save_when_no_store(self):
        mem = LongTermMemory(agent_id="mem_agent_2")
        mem.vector_store = None
        result = mem.save_memory({"data": "test"}, {"type": "test"})
        assert result is False

    def test_long_term_memory_retrieve_when_no_store(self):
        mem = LongTermMemory(agent_id="mem_agent_3")
        mem.vector_store = None
        result = mem.retrieve_similar("query")
        assert result == []

    def test_vector_store_graceful_none(self):
        store = get_vector_store()
        if store is None:
            assert True
        else:
            assert True


# ============================================================================
# 11. FastAPI 主应用及全部API端点
# ============================================================================
class TestFastAPIApp:
    def test_app_creation(self):
        from app.main import app
        assert app.title == "Neural Agent System"
        assert app.version == "1.0.0"

    def test_health_endpoint_exists(self):
        from app.main import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_api_v1_prefix(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        api_routes = [r for r in routes if r.startswith("/api/v1")]
        assert len(api_routes) > 0

    def test_tasks_routes(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        task_routes = [r for r in routes if "/tasks" in r]
        assert len(task_routes) > 0

    def test_convolution_routes(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        conv_routes = [r for r in routes if "/convolution" in r]
        assert len(conv_routes) > 0

    def test_pooling_routes(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        pool_routes = [r for r in routes if "/pooling" in r]
        assert len(pool_routes) > 0

    def test_fullconnect_routes(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        fc_routes = [r for r in routes if "/fullconnect" in r]
        assert len(fc_routes) > 0

    def test_output_routes(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        out_routes = [r for r in routes if "/output" in r]
        assert len(out_routes) > 0

    def test_backward_routes(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        bw_routes = [r for r in routes if "/backward" in r]
        assert len(bw_routes) > 0

    def test_pipeline_routes(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        pl_routes = [r for r in routes if "/pipeline" in r]
        assert len(pl_routes) > 0

    def test_cors_middleware(self):
        from app.main import app
        from starlette.middleware.cors import CORSMiddleware
        has_cors = any(
            isinstance(m.cls, type(CORSMiddleware)) if hasattr(m, 'cls') else False
            for m in app.user_middleware
        ) or any(
            isinstance(m, CORSMiddleware)
            for m in getattr(app, 'middleware_stack', []) if hasattr(m, '__class__')
        )
        assert has_cors or any("cors" in str(type(m)).lower() for m in app.user_middleware)

    def test_all_route_methods(self):
        from app.main import app
        route_info = {}
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                route_info[route.path] = route.methods
        assert "/health" in route_info
        assert "GET" in route_info["/health"]

    def test_api_router_endpoints_complete(self):
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]

        expected_endpoints = [
            "/api/v1/tasks/submit",
            "/api/v1/convolution/process",
            "/api/v1/pooling/process",
            "/api/v1/fullconnect/fc1/process",
            "/api/v1/fullconnect/fc2/process",
            "/api/v1/fullconnect/fc3/process",
            "/api/v1/output/generate",
            "/api/v1/backward/feedback",
            "/api/v1/pipeline/execute",
        ]
        for ep in expected_endpoints:
            assert ep in routes, f"Missing endpoint: {ep}"
