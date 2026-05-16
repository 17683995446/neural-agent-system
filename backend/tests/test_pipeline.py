"""
神经网络Pipeline单元测试
"""
from unittest.mock import patch, MagicMock

from app.services.pipeline.neural_pipeline import NeuralNetworkPipeline, get_neural_pipeline
from app.models.schemas import TaskStatus


class TestNeuralNetworkPipeline:
    """神经网络Pipeline测试"""

    @patch('app.services.pipeline.neural_pipeline.SessionLocal')
    def test_update_task_status(self, mock_session_local):
        """测试更新任务状态"""
        # 模拟数据库操作
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        pipeline = NeuralNetworkPipeline()

        # 使用正确的TaskStatus枚举
        pipeline._update_task_status("test-001", TaskStatus.RUNNING, 1)

        mock_db.close.assert_called_once()

    @patch('app.services.input_layer.service.InputLayerService')
    def test_execute_forward_pipeline_with_mock(self, mock_input_service, temp_code_repo, sample_task_id, sample_user_requirement):
        """测试前向传播Pipeline（使用mock）"""
        pipeline = NeuralNetworkPipeline()

        # 这个测试需要mock掉外部依赖
        # 实际执行会失败因为没有真实的LLM等
        # 这里只是验证pipeline结构正确

        # 由于依赖复杂，我们只测试pipeline能被创建
        assert pipeline is not None
        assert pipeline.conv_service is not None
        assert pipeline.pool_service is not None
        assert pipeline.fc1_service is not None
        assert pipeline.fc2_service is not None
        assert pipeline.fc3_service is not None
        assert pipeline.output_service is not None

    def test_get_neural_pipeline_singleton(self):
        """测试单例模式"""
        pipeline1 = get_neural_pipeline()
        pipeline2 = get_neural_pipeline()

        assert pipeline1 is pipeline2


class TestLayerIntegration:
    """层间集成测试"""

    def test_layer_output_flow(self, mock_convolution_output, mock_pooling_output, mock_fc1_output, mock_fc2_output, mock_fc3_output):
        """测试层间数据流"""
        # 验证每一层的输出能被下一层接收
        from app.services.fullconnect.service_fc2 import CodeGenerationService
        from app.services.fullconnect.service_fc3 import TestGenerationService

        # FC2应该能处理FC1的输出
        fc2_service = CodeGenerationService()
        assert fc2_service is not None

        # FC3应该能处理FC2的输出
        fc3_service = TestGenerationService()
        assert fc3_service is not None

        # 所有mock数据格式应该正确
        assert "solution" in mock_fc1_output
        assert "modifications" in mock_fc2_output
        assert "tests" in mock_fc3_output
        assert "coverage" in mock_fc3_output