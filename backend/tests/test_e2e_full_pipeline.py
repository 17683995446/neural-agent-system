"""
端到端全流程验证测试
验证 Input→Conv→Pool→FC1→FC2→FC3→Output→Backward 完整链路
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from app.services.convolution.service import ConvolutionLayerService
from app.services.pooling.service import PoolingLayerService
from app.services.fullconnect.service_fc1 import GlobalUnderstandingService
from app.services.fullconnect.service_fc2 import CodeGenerationService
from app.services.fullconnect.service_fc3 import TestGenerationService
from app.services.output.service import OutputLayerService
from app.services.backward.service import BackwardPropagationService
from app.agents.trust.backward import (
    RewardCalculator,
    TrustWeightUpdater,
    BackwardPropagation,
)


@pytest.fixture
def sample_code_repo():
    tmpdir = Path(tempfile.mkdtemp(prefix="test_repo_"))
    src_dir = tmpdir / "src"
    src_dir.mkdir()

    (src_dir / "main.py").write_text(
        'def hello():\n    return "hello"\n\ndef add(a, b):\n    return a + b\n'
    )
    (src_dir / "utils.py").write_text(
        "import os\n\ndef validate(data):\n    return bool(data)\n\nclass Helper:\n    def process(self):\n        pass\n"
    )
    (tmpdir / "README.md").write_text("# Test Project\n")

    yield str(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def task_id():
    return "e2e_test_001"


@pytest.fixture
def user_requirement():
    return "Add error handling to all functions"


class TestFullForwardPipeline:
    def test_convolution_layer(self, sample_code_repo, task_id):
        service = ConvolutionLayerService()
        result = service.process_task(task_id, sample_code_repo)

        assert result["task_id"] == task_id
        assert result["layer"] == "convolution"
        assert "analyzed_files" in result
        assert len(result["analyzed_files"]) >= 2

        functions_found = sum(
            len(f.get("functions", [])) for f in result["analyzed_files"]
        )
        classes_found = sum(
            len(f.get("classes", [])) for f in result["analyzed_files"]
        )
        assert functions_found > 0, "Should detect functions in code repo"
        assert classes_found > 0, "Should detect classes in code repo"

        print(f"  [CONV] {len(result['analyzed_files'])} files, {functions_found} funcs, {classes_found} classes")
        return result

    def test_pooling_layer(self, sample_code_repo, task_id, user_requirement):
        conv_service = ConvolutionLayerService()
        conv_output = conv_service.process_task(task_id, sample_code_repo)

        pool_service = PoolingLayerService()
        result = pool_service.process_task(task_id, conv_output, user_requirement)

        assert result["task_id"] == task_id
        assert result["layer"] == "pooling"
        assert "compressed_features" in result
        assert "global_features" in result

        print(f"  [POOL] {result['total_files_processed']} compressed, global_features keys: {list(result['global_features'].keys())}")
        return result

    def test_fc1_global_understanding(self, sample_code_repo, task_id, user_requirement):
        conv_service = ConvolutionLayerService()
        conv_output = conv_service.process_task(task_id, sample_code_repo)

        pool_service = PoolingLayerService()
        pool_output = pool_service.process_task(task_id, conv_output, user_requirement)

        fc1_service = GlobalUnderstandingService()
        result = fc1_service.process_task(task_id, pool_output, user_requirement)

        assert result["task_id"] == task_id
        assert result["layer"] == "global_understanding"
        assert "solution" in result
        assert "overview" in result["solution"]
        assert "modification_list" in result["solution"]
        assert "architecture" in result["solution"]

        print(f"  [FC1] {len(result['solution']['modification_list'])} modifications planned")
        return result

    def test_fc2_code_generation(self, sample_code_repo, task_id, user_requirement):
        conv_service = ConvolutionLayerService()
        conv_output = conv_service.process_task(task_id, sample_code_repo)

        pool_service = PoolingLayerService()
        pool_output = pool_service.process_task(task_id, conv_output, user_requirement)

        fc1_service = GlobalUnderstandingService()
        fc1_output = fc1_service.process_task(task_id, pool_output, user_requirement)

        fc2_service = CodeGenerationService()
        result = fc2_service.process_task(task_id, fc1_output, sample_code_repo)

        assert result["task_id"] == task_id
        assert result["layer"] == "code_generation"
        assert "modifications" in result
        assert "summary" in result
        assert result["summary"]["total_modifications"] >= 0

        print(f"  [FC2] {result['summary']['successful']} success, {result['summary']['failed']} failed")
        return result

    def test_fc3_test_generation(self, sample_code_repo, task_id, user_requirement):
        conv_service = ConvolutionLayerService()
        conv_output = conv_service.process_task(task_id, sample_code_repo)

        pool_service = PoolingLayerService()
        pool_output = pool_service.process_task(task_id, conv_output, user_requirement)

        fc1_service = GlobalUnderstandingService()
        fc1_output = fc1_service.process_task(task_id, pool_output, user_requirement)

        fc2_service = CodeGenerationService()
        fc2_output = fc2_service.process_task(task_id, fc1_output, sample_code_repo)

        fc3_service = TestGenerationService()
        result = fc3_service.process_task(task_id, fc2_output)

        assert result["task_id"] == task_id
        assert result["layer"] == "test_generation"
        assert "tests" in result
        assert "coverage" in result
        assert "summary" in result

        print(f"  [FC3] {result['summary']['total_tests']} tests generated, coverage: {result['coverage'].get('coverage_percent', 0)}%")
        return result

    def test_output_layer(self, sample_code_repo, task_id, user_requirement):
        conv_service = ConvolutionLayerService()
        conv_output = conv_service.process_task(task_id, sample_code_repo)

        pool_service = PoolingLayerService()
        pool_output = pool_service.process_task(task_id, conv_output, user_requirement)

        fc1_service = GlobalUnderstandingService()
        fc1_output = fc1_service.process_task(task_id, pool_output, user_requirement)

        fc2_service = CodeGenerationService()
        fc2_output = fc2_service.process_task(task_id, fc1_output, sample_code_repo)

        fc3_service = TestGenerationService()
        fc3_output = fc3_service.process_task(task_id, fc2_output)

        output_service = OutputLayerService()
        result = output_service.process_task(
            task_id, user_requirement, fc1_output, fc2_output, fc3_output, 1000.0
        )

        assert result["task_id"] == task_id
        assert result["layer"] == "output"
        assert "document_path" in result

        doc_path = Path(result["document_path"])
        assert doc_path.exists(), f"Document file should exist at {doc_path}"
        doc_content = doc_path.read_text(encoding="utf-8")
        assert len(doc_content) > 0
        assert "代码修改任务报告" in doc_content or "任务" in doc_content

        print(f"  [OUTPUT] Document saved to {result['document_path']}, size: {len(doc_content)} chars")
        return result

    def test_complete_forward_pipeline(self, sample_code_repo, task_id, user_requirement):
        print("\n=== Full Forward Pipeline ===")

        conv_service = ConvolutionLayerService()
        conv_output = conv_service.process_task(task_id, sample_code_repo)
        assert conv_output["layer"] == "convolution"
        print(f"  [CONV] OK - {len(conv_output['analyzed_files'])} files")

        pool_service = PoolingLayerService()
        pool_output = pool_service.process_task(task_id, conv_output, user_requirement)
        assert pool_output["layer"] == "pooling"
        print(f"  [POOL] OK - {pool_output['total_files_processed']} files processed")

        fc1_service = GlobalUnderstandingService()
        fc1_output = fc1_service.process_task(task_id, pool_output, user_requirement)
        assert fc1_output["layer"] == "global_understanding"
        print(f"  [FC1]  OK - {len(fc1_output['solution']['modification_list'])} modifications")

        fc2_service = CodeGenerationService()
        fc2_output = fc2_service.process_task(task_id, fc1_output, sample_code_repo)
        assert fc2_output["layer"] == "code_generation"
        print(f"  [FC2]  OK - {fc2_output['summary']['successful']} successful")

        fc3_service = TestGenerationService()
        fc3_output = fc3_service.process_task(task_id, fc2_output)
        assert fc3_output["layer"] == "test_generation"
        print(f"  [FC3]  OK - {fc3_output['summary']['total_tests']} tests")

        output_service = OutputLayerService()
        result = output_service.process_task(
            task_id, user_requirement, fc1_output, fc2_output, fc3_output, 500.0
        )
        assert result["layer"] == "output"
        assert Path(result["document_path"]).exists()
        print(f"  [OUT]  OK - Document at {result['document_path']}")

        print("=== Forward Pipeline Complete ===\n")


class TestBackwardPipeline:
    def test_reward_calculation(self):
        calc = RewardCalculator()

        reward_neutral = calc.calculate_reward({"satisfaction_score": 3})
        assert reward_neutral == 0.0

        reward_positive = calc.calculate_reward({"satisfaction_score": 5})
        assert reward_positive == 1.0

        reward_negative = calc.calculate_reward({"satisfaction_score": 0})
        assert reward_negative == -1.0

        reward_with_items = calc.calculate_reward({
            "satisfaction_score": 4,
            "feedback_items": [
                {"type": "positive"},
                {"type": "negative"},
            ]
        })
        assert -1.0 <= reward_with_items <= 1.0

        print(f"  [REWARD] neutral={reward_neutral}, positive={reward_positive}, negative={reward_negative}, mixed={reward_with_items:.2f}")

    def test_trust_weight_update(self):
        updater = TrustWeightUpdater(learning_rate=0.1, clip_param=0.2)

        current_weights = {"agent_a": 1.0, "agent_b": 1.0}
        rewards = {"agent_a": 0.5, "agent_b": -0.3}

        new_weights = updater.update_weights(current_weights, rewards, iteration=0)

        assert "agent_a" in new_weights
        assert "agent_b" in new_weights
        assert new_weights["agent_a"] > current_weights["agent_a"]
        assert new_weights["agent_b"] < current_weights["agent_b"]
        assert 0.0 <= new_weights["agent_a"] <= 2.0
        assert 0.0 <= new_weights["agent_b"] <= 2.0

        print(f"  [TRUST] agent_a: 1.0 -> {new_weights['agent_a']:.3f}, agent_b: 1.0 -> {new_weights['agent_b']:.3f}")

    def test_backward_propagation(self, task_id):
        bp = BackwardPropagation()

        layer_agents = {
            "convolution": ["conv_1"],
            "pooling": ["pool_1"],
            "global_understanding": ["fc1_1"],
            "code_generation": ["fc2_1"],
            "test_generation": ["fc3_1"],
            "output": ["out_1"],
        }

        user_feedback = {
            "satisfaction_score": 4,
            "feedback_items": [{"type": "positive"}]
        }

        result = bp.propagate_feedback(
            task_id=task_id,
            user_feedback=user_feedback,
            layer_agents=layer_agents,
            current_iteration=1
        )

        assert len(result) > 0
        print(f"  [BACKWARD] {len(result)} agents updated")

    def test_backward_service(self, task_id):
        service = BackwardPropagationService()

        user_feedback = {
            "satisfaction_score": 4,
            "feedback_items": [{"type": "positive"}],
            "comments": "Good result",
            "iteration_number": 1
        }

        result = service.process_user_feedback(task_id, user_feedback)

        assert result["task_id"] == task_id
        assert result["layer"] == "backward_propagation"
        assert "reward" in result
        assert "updated_weights" in result
        assert -1.0 <= result["reward"] <= 1.0

        print(f"  [BACKWARD SVC] reward={result['reward']:.3f}, {len(result['updated_weights'])} weights updated")

    def test_layer_reward_calculation(self, task_id):
        service = BackwardPropagationService()

        user_feedback = {"satisfaction_score": 5}
        rewards = service.calculate_layer_rewards(task_id, user_feedback)

        assert "convolution" in rewards
        assert "output" in rewards
        assert rewards["output"] >= rewards["convolution"]

        print(f"  [LAYER REWARDS] conv={rewards['convolution']:.2f}, output={rewards['output']:.2f}")


class TestServiceInitialization:
    def test_convolution_service_init(self):
        service = ConvolutionLayerService()
        assert service.code_analyzer is not None

    def test_pooling_service_init(self):
        service = PoolingLayerService()
        assert service.compressor is not None
        assert service.aggregator is not None

    def test_fc1_service_init(self):
        service = GlobalUnderstandingService()
        assert service.planner is not None

    def test_fc2_service_init(self):
        service = CodeGenerationService()
        assert service.modifier is not None
        assert service.filter is not None

    def test_fc3_service_init(self):
        service = TestGenerationService()
        assert service.generator is not None
        assert service.coverage_analyzer is not None

    def test_output_service_init(self):
        service = OutputLayerService()
        assert service.template is not None

    def test_backward_service_init(self):
        service = BackwardPropagationService()
        assert service.reward_calculator is not None
        assert service.weight_updater is not None
        assert service.backward_propagation is not None
        assert service.feedback_processor is not None

    def test_backward_propagation_init(self):
        bp = BackwardPropagation()
        assert bp.reward_calculator is not None
        assert bp.weight_updater is not None


class TestAPIRoutesRegistration:
    def test_all_routes_registered(self):
        from app.main import app
        route_paths = [r.path for r in app.routes if hasattr(r, 'path')]

        expected_prefixes = [
            "/health",
            "/api/v1/tasks",
            "/api/v1/convolution",
            "/api/v1/pooling",
            "/api/v1/fullconnect",
            "/api/v1/output",
            "/api/v1/backward",
            "/api/v1/pipeline",
        ]

        for prefix in expected_prefixes:
            matching = [p for p in route_paths if p.startswith(prefix)]
            assert len(matching) > 0, f"No routes registered for prefix {prefix}"

        print(f"  [ROUTES] {len(route_paths)} routes registered, all prefixes verified")


class TestOutputFilesIntegrity:
    def test_pipeline_output_files_created(self, sample_code_repo, task_id, user_requirement):
        conv_service = ConvolutionLayerService()
        conv_output = conv_service.process_task(task_id, sample_code_repo)

        pool_service = PoolingLayerService()
        pool_output = pool_service.process_task(task_id, conv_output, user_requirement)

        fc1_service = GlobalUnderstandingService()
        fc1_output = fc1_service.process_task(task_id, pool_output, user_requirement)

        fc2_service = CodeGenerationService()
        fc2_output = fc2_service.process_task(task_id, fc1_output, sample_code_repo)

        fc3_service = TestGenerationService()
        fc3_output = fc3_service.process_task(task_id, fc2_output)

        output_service = OutputLayerService()
        output_service.process_task(
            task_id, user_requirement, fc1_output, fc2_output, fc3_output, 500.0
        )

        task_dir = Path("task_output") / task_id

        expected_files = [
            "convolution/analysis_results.json",
            "pooling/pooling_results.json",
            "global_understanding/solution.json",
            "code_generation/modifications.json",
            "test_generation/test_cases.json",
            "output/task_report.md",
        ]

        for rel_path in expected_files:
            file_path = task_dir / rel_path
            assert file_path.exists(), f"Expected output file missing: {file_path}"

            if file_path.suffix == ".json":
                data = json.loads(file_path.read_text(encoding="utf-8"))
                assert "task_id" in data, f"JSON output missing task_id: {file_path}"
                assert data["task_id"] == task_id, f"task_id mismatch in {file_path}"

        print(f"  [FILES] All {len(expected_files)} output files verified")
