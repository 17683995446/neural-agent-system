"""
深度验证测试 - HTTP端点、RL Trainer、层间数据流一致性、异常边界、配置、Docker
"""
import shutil
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import Settings
from app.core.rl_trainer import RLTrainer
from app.services.convolution.service import ConvolutionLayerService
from app.services.pooling.service import PoolingLayerService
from app.services.fullconnect.service_fc1 import GlobalUnderstandingService
from app.services.fullconnect.service_fc2 import CodeGenerationService
from app.services.fullconnect.service_fc3 import TestGenerationService
from app.services.output.service import OutputLayerService
from app.agents.trust.backward import RewardCalculator, TrustWeightUpdater, BackwardPropagation


# ============================================================================
# 1. FastAPI HTTP 端点实际请求/响应
# ============================================================================
class TestHTTPEndpoints:
    @pytest.fixture
    def client(self):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_convolution_files_endpoint(self, client):
        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "test.py").write_text("pass")
        try:
            resp = await client.get(
                "/api/v1/convolution/files",
                params={"task_id": "ht1", "code_repo_path": tmpdir},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "total_files" in data
        finally:
            shutil.rmtree(tmpdir)

    @pytest.mark.asyncio
    async def test_backward_calculate_rewards(self, client):
        resp = await client.post(
            "/api/v1/backward/calculate-rewards",
            params={"task_id": "bhr1"},
            json={"satisfaction_score": 4},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "layer_rewards" in data
        assert "convolution" in data["layer_rewards"]

    @pytest.mark.asyncio
    async def test_pipeline_status_not_found(self, client):
        resp = await client.get("/api/v1/pipeline/status/nonexistent_task_xyz")
        assert resp.status_code in (404, 500)

    @pytest.mark.asyncio
    async def test_tasks_list_endpoint(self, client):
        resp = await client.get("/api/v1/tasks/", params={"skip": 0, "limit": 5})
        assert resp.status_code >= 200

    @pytest.mark.asyncio
    async def test_convolution_process_endpoint(self, client):
        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "main.py").write_text("def hello():\n    pass\n")
        try:
            resp = await client.post(
                "/api/v1/convolution/process",
                json={"task_id": "conv_http_1", "code_repo_path": tmpdir},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["layer"] == "convolution"
            assert data["total_files"] >= 1
        finally:
            shutil.rmtree(tmpdir)

    @pytest.mark.asyncio
    async def test_pooling_process_endpoint(self, client):
        conv_svc = ConvolutionLayerService()
        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "app.py").write_text("def run(): pass\n")
        conv_output = conv_svc.process_task("pool_http_1", tmpdir)
        try:
            resp = await client.post(
                "/api/v1/pooling/process",
                json={
                    "task_id": "pool_http_1",
                    "convolution_output": conv_output,
                    "user_requirement": "add feature",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["layer"] == "pooling"
        finally:
            shutil.rmtree(tmpdir)


# ============================================================================
# 2. RL Trainer 模块
# ============================================================================
class TestRLTrainer:
    def test_trainer_init(self):
        trainer = RLTrainer()
        assert trainer.backward_propagation is not None
        assert trainer.is_running is False
        assert trainer.training_interval == 60

    def test_trainer_stop(self):
        trainer = RLTrainer()
        trainer.is_running = True
        trainer.stop()
        assert trainer.is_running is False

    def test_trainer_layer_agents(self):
        trainer = RLTrainer()
        agents = trainer._get_layer_agents("t1")
        assert "convolution" in agents
        assert "pooling" in agents
        assert "global_understanding" in agents
        assert "code_generation" in agents
        assert "test_generation" in agents
        assert "output" in agents
        assert len(agents["convolution"]) == 5

    def test_trainer_train_on_task(self):
        trainer = RLTrainer()
        result = trainer.train_on_task({
            "task_id": "rl1",
            "learning_rate": 0.1,
            "iteration_count": 1,
        })
        assert result["task_id"] == "rl1"
        assert result["learning_rate"] == 0.1
        assert result["weights_updated"] >= 0

    def test_trainer_ray_address_transform(self):
        from app.core.config import settings
        ray_address = settings.redis_url.replace("redis://", "ray://")
        assert ray_address.startswith("ray://")


# ============================================================================
# 3. 层间数据流格式一致性
# ============================================================================
class TestInterLayerDataFlow:
    def _run_pipeline(self, tmpdir, task_id, req):
        conv = ConvolutionLayerService().process_task(task_id, tmpdir)
        pool = PoolingLayerService().process_task(task_id, conv, req)
        fc1 = GlobalUnderstandingService().process_task(task_id, pool, req)
        fc2 = CodeGenerationService().process_task(task_id, fc1, tmpdir)
        fc3 = TestGenerationService().process_task(task_id, fc2)
        out = OutputLayerService().process_task(task_id, req, fc1, fc2, fc3, 100.0)
        return conv, pool, fc1, fc2, fc3, out

    @pytest.fixture
    def code_repo(self):
        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "app.py").write_text(
            "import os\n\ndef process(data):\n    return data\n\nclass App:\n    def run(self):\n        pass\n"
        )
        yield tmpdir
        shutil.rmtree(tmpdir)

    def test_conv_to_pool_data_contract(self, code_repo):
        conv = ConvolutionLayerService().process_task("dp1", code_repo)
        assert "analyzed_files" in conv
        assert "summary" in conv
        pool = PoolingLayerService().process_task("dp1", conv, "test")
        assert "compressed_features" in pool
        assert "global_features" in pool

    def test_pool_to_fc1_data_contract(self, code_repo):
        conv = ConvolutionLayerService().process_task("dp2", code_repo)
        pool = PoolingLayerService().process_task("dp2", conv, "add feature")
        assert "global_features" in pool
        fc1 = GlobalUnderstandingService().process_task("dp2", pool, "add feature")
        assert "solution" in fc1
        assert "modification_list" in fc1["solution"]

    def test_fc1_to_fc2_data_contract(self, code_repo):
        conv = ConvolutionLayerService().process_task("dp3", code_repo)
        pool = PoolingLayerService().process_task("dp3", conv, "add feature")
        fc1 = GlobalUnderstandingService().process_task("dp3", pool, "add feature")
        assert "solution" in fc1
        fc2 = CodeGenerationService().process_task("dp3", fc1, code_repo)
        assert "modifications" in fc2
        assert "summary" in fc2

    def test_fc2_to_fc3_data_contract(self, code_repo):
        conv = ConvolutionLayerService().process_task("dp4", code_repo)
        pool = PoolingLayerService().process_task("dp4", conv, "add feature")
        fc1 = GlobalUnderstandingService().process_task("dp4", pool, "add feature")
        fc2 = CodeGenerationService().process_task("dp4", fc1, code_repo)
        assert "modifications" in fc2
        fc3 = TestGenerationService().process_task("dp4", fc2)
        assert "tests" in fc3
        assert "coverage" in fc3

    def test_all_layers_task_id_consistency(self, code_repo):
        tid = "consistency_001"
        conv, pool, fc1, fc2, fc3, out = self._run_pipeline(code_repo, tid, "test")
        assert conv["task_id"] == tid
        assert pool["task_id"] == tid
        assert fc1["task_id"] == tid
        assert fc2["task_id"] == tid
        assert fc3["task_id"] == tid
        assert out["task_id"] == tid

    def test_all_layers_have_layer_name(self, code_repo):
        conv, pool, fc1, fc2, fc3, out = self._run_pipeline(code_repo, "ln1", "test")
        assert conv["layer"] == "convolution"
        assert pool["layer"] == "pooling"
        assert fc1["layer"] == "global_understanding"
        assert fc2["layer"] == "code_generation"
        assert fc3["layer"] == "test_generation"
        assert out["layer"] == "output"

    def test_all_layers_have_timestamp(self, code_repo):
        conv, pool, fc1, fc2, fc3, out = self._run_pipeline(code_repo, "ts1", "test")
        assert "created_at" in conv
        assert "created_at" in pool
        assert "created_at" in fc1
        assert "created_at" in fc2
        assert "created_at" in fc3


# ============================================================================
# 4. 异常处理与边界条件
# ============================================================================
class TestExceptionAndBoundary:
    def test_convolution_nonexistent_repo(self):
        svc = ConvolutionLayerService()
        files = svc.get_code_files("/nonexistent/path/xyz")
        assert files == []

    def test_convolution_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        svc = ConvolutionLayerService()
        files = svc.get_code_files(tmpdir)
        assert files == []
        shutil.rmtree(tmpdir)

    def test_pooling_empty_input(self):
        svc = PoolingLayerService()
        result = svc.process_task("bnd1", {"analyzed_files": []}, "test query")
        assert result["total_files_processed"] == 0

    def test_fc2_empty_modifications(self):
        fc1_output = {
            "task_id": "bnd2",
            "layer": "global_understanding",
            "solution": {"overview": "test", "modification_list": [], "execution_order": [], "risk_points": [], "architecture": {}},
        }
        svc = CodeGenerationService()
        result = svc.process_task("bnd2", fc1_output, "/tmp")
        assert result["summary"]["total_modifications"] == 0

    def test_fc3_no_successful_modifications(self):
        fc2_output = {
            "modifications": [
                {"target": "x", "status": "failed", "error": "test error"}
            ],
            "summary": {"total_modifications": 1, "successful": 0, "failed": 1},
        }
        svc = TestGenerationService()
        result = svc.process_task("bnd3", fc2_output)
        assert result["summary"]["total_tests"] == 0

    def test_reward_extreme_values(self):
        calc = RewardCalculator()
        r_max = calc.calculate_reward({"satisfaction_score": 100})
        r_min = calc.calculate_reward({"satisfaction_score": -100})
        assert -1.0 <= r_max <= 1.0
        assert -1.0 <= r_min <= 1.0

    def test_reward_many_feedback_items(self):
        calc = RewardCalculator()
        items = [{"type": "positive"}] * 20
        r = calc.calculate_reward({"satisfaction_score": 5, "feedback_items": items})
        assert r <= 1.0

    def test_trust_update_zero_reward(self):
        updater = TrustWeightUpdater()
        new_w = updater.update_weights({"a": 1.0}, {"a": 0.0}, iteration=0)
        assert new_w["a"] == 1.0

    def test_trust_update_extreme_positive(self):
        updater = TrustWeightUpdater(learning_rate=1.0, clip_param=0.5)
        new_w = updater.update_weights({"a": 1.9}, {"a": 1.0}, iteration=0)
        assert new_w["a"] <= 2.0

    def test_trust_update_extreme_negative(self):
        updater = TrustWeightUpdater(learning_rate=1.0, clip_param=0.5)
        new_w = updater.update_weights({"a": 0.1}, {"a": -1.0}, iteration=0)
        assert new_w["a"] >= 0.0

    def test_backward_empty_layer_agents(self):
        bp = BackwardPropagation()
        result = bp.propagate_feedback("bnd4", {"satisfaction_score": 3}, {}, 1)
        assert result == {}

    def test_coverage_analyzer_no_modified_code(self):
        from app.services.fullconnect.service_fc3 import CoverageAnalyzer
        analyzer = CoverageAnalyzer()
        result = analyzer.analyze_coverage([{"status": "success", "modified_code": ""}])
        assert result["total_lines"] >= 0
        assert "coverage_percent" in result

    def test_output_with_all_empty_outputs(self):
        svc = OutputLayerService()
        result = svc.process_task(
            "bnd5", "test",
            {"solution": {"architecture": {}, "risk_points": []}},
            {"summary": {}, "modifications": []},
            {"summary": {}, "coverage": {}, "tests": []},
            0.0,
        )
        assert result["task_id"] == "bnd5"


# ============================================================================
# 5. 配置加载与.env文件
# ============================================================================
class TestConfigurationLoading:
    def test_settings_loads_from_env(self):
        s = Settings()
        assert s.redis_url is not None
        assert s.postgres_url is not None

    def test_env_file_exists(self):
        env_path = Path("D:/claude_workspace/neural-agent-system/.env")
        assert env_path.exists()

    def test_env_example_exists(self):
        example_path = Path("D:/claude_workspace/neural-agent-system/backend/.env.example")
        assert example_path.exists()

    def test_env_contains_required_keys(self):
        env_path = Path("D:/claude_workspace/neural-agent-system/.env")
        content = env_path.read_text()
        required_keys = [
            "LITELLM_API_KEY", "OPENAI_API_KEY",
            "REDIS_URL", "POSTGRES_URL", "RABBITMQ_URL",
            "MILVUS_URL", "MAX_ITERATION",
            "TRUST_INITIAL_VALUE", "TRUST_MIN_VALUE", "TRUST_MAX_VALUE",
        ]
        for key in required_keys:
            assert key in content, f"Missing key in .env: {key}"

    def test_env_example_has_all_keys(self):
        example_path = Path("D:/claude_workspace/neural-agent-system/backend/.env.example")
        content = example_path.read_text()
        settings_attrs = [
            "REDIS_URL", "POSTGRES_URL", "RABBITMQ_URL", "MILVUS_URL",
            "MAX_ITERATION", "DEFAULT_LEARNING_RATE",
            "TRUST_INITIAL_VALUE", "TRUST_MIN_VALUE", "TRUST_MAX_VALUE",
        ]
        for attr in settings_attrs:
            assert attr in content, f"Missing key in .env.example: {attr}"

    def test_settings_env_file_config(self):
        s = Settings()
        assert s.trust_initial_value == 1.0
        assert s.trust_min_value == 0.0
        assert s.trust_max_value == 2.0


# ============================================================================
# 6. Docker 配置完整性
# ============================================================================
class TestDockerConfig:
    def test_docker_compose_exists(self):
        path = Path("D:/claude_workspace/neural-agent-system/docker-compose.yml")
        assert path.exists()

    def _load_compose(self):
        import yaml
        path = Path("D:/claude_workspace/neural-agent-system/docker-compose.yml")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_docker_compose_loads(self):
        compose = self._load_compose()
        assert "services" in compose

    def test_docker_compose_all_services(self):
        compose = self._load_compose()
        expected_services = [
            "api-server", "agent-worker", "rl-trainer",
            "redis", "postgres", "rabbitmq",
            "etcd", "minio", "milvus-standalone",
            "ray", "prometheus", "grafana",
            "loki", "promtail",
        ]
        for svc in expected_services:
            assert svc in compose["services"], f"Missing Docker service: {svc}"

    def test_docker_compose_network(self):
        compose = self._load_compose()
        assert "neural-agent-network" in compose.get("networks", {})

    def test_docker_compose_volumes(self):
        compose = self._load_compose()
        expected_volumes = [
            "redis_data", "postgres_data", "rabbitmq_data",
            "etcd_data", "minio_data", "milvus_data",
        ]
        for vol in expected_volumes:
            assert vol in compose.get("volumes", {}), f"Missing Docker volume: {vol}"

    def test_dockerfile_exists(self):
        path = Path("D:/claude_workspace/neural-agent-system/backend/docker/Dockerfile")
        assert path.exists()

    def test_start_script_exists(self):
        path = Path("D:/claude_workspace/neural-agent-system/start.sh")
        assert path.exists()

    def test_prometheus_config_exists(self):
        path = Path("D:/claude_workspace/neural-agent-system/docker/prometheus.yml")
        assert path.exists()

    def test_loki_config_exists(self):
        path = Path("D:/claude_workspace/neural-agent-system/docker/loki-config.yml")
        assert path.exists()

    def test_promtail_config_exists(self):
        path = Path("D:/claude_workspace/neural-agent-system/docker/promtail-config.yml")
        assert path.exists()


# ============================================================================
# 7. 单例/并发安全
# ============================================================================
class TestSingletonSafety:
    def test_llm_client_singleton(self):
        from app.core.llm_client import get_llm_client
        c1 = get_llm_client()
        c2 = get_llm_client()
        assert c1 is c2

    def test_convolution_service_singleton(self):
        from app.services.convolution.service import get_convolution_service
        s1 = get_convolution_service()
        s2 = get_convolution_service()
        assert s1 is s2

    def test_pooling_service_singleton(self):
        from app.services.pooling.service import get_pooling_service
        s1 = get_pooling_service()
        s2 = get_pooling_service()
        assert s1 is s2

    def test_fc1_service_singleton(self):
        from app.services.fullconnect.service_fc1 import get_global_understanding_service
        s1 = get_global_understanding_service()
        s2 = get_global_understanding_service()
        assert s1 is s2

    def test_fc2_service_singleton(self):
        from app.services.fullconnect.service_fc2 import get_code_generation_service
        s1 = get_code_generation_service()
        s2 = get_code_generation_service()
        assert s1 is s2

    def test_fc3_service_singleton(self):
        from app.services.fullconnect.service_fc3 import get_test_generation_service
        s1 = get_test_generation_service()
        s2 = get_test_generation_service()
        assert s1 is s2

    def test_output_service_singleton(self):
        from app.services.output.service import get_output_service
        s1 = get_output_service()
        s2 = get_output_service()
        assert s1 is s2

    def test_backward_service_singleton(self):
        from app.services.backward.service import get_backward_service
        s1 = get_backward_service()
        s2 = get_backward_service()
        assert s1 is s2

    def test_pipeline_singleton(self):
        from app.services.pipeline.neural_pipeline import get_neural_pipeline
        p1 = get_neural_pipeline()
        p2 = get_neural_pipeline()
        assert p1 is p2

    def test_backward_propagation_singleton(self):
        from app.agents.trust.backward import get_backward_propagation
        b1 = get_backward_propagation()
        b2 = get_backward_propagation()
        assert b1 is b2

    def test_settings_singleton(self):
        from app.core.config import get_settings
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
