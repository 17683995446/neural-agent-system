"""
信任度管理单元测试
"""

from app.agents.trust.backward import (
    RewardCalculator,
    TrustWeightUpdater,
    BackwardPropagation
)


class TestRewardCalculator:
    """奖励计算器测试"""

    def test_calculate_reward_neutral(self):
        """测试中性反馈"""
        calculator = RewardCalculator()

        feedback = {
            "satisfaction_score": 3,  # 中间值
            "feedback_items": []
        }

        reward = calculator.calculate_reward(feedback)

        assert reward == 0.0  # 3分映射到0

    def test_calculate_reward_positive(self):
        """测试正向反馈"""
        calculator = RewardCalculator()

        feedback = {
            "satisfaction_score": 5,  # 满分
            "feedback_items": [
                {"type": "positive", "description": "效果很好"}
            ]
        }

        reward = calculator.calculate_reward(feedback)

        assert reward > 0

    def test_calculate_reward_negative(self):
        """测试负向反馈"""
        calculator = RewardCalculator()

        feedback = {
            "satisfaction_score": 1,
            "feedback_items": [
                {"type": "negative", "description": "有bug"}
            ]
        }

        reward = calculator.calculate_reward(feedback)

        assert reward < 0

    def test_reward_clamped(self):
        """测试奖励值限制"""
        calculator = RewardCalculator()

        feedback = {
            "satisfaction_score": 5,
            "feedback_items": [
                {"type": "positive", "description": "很好"} for _ in range(10)
            ]
        }

        reward = calculator.calculate_reward(feedback)

        assert -1.0 <= reward <= 1.0


class TestTrustWeightUpdater:
    """信任度权重更新器测试"""

    def test_update_weights_basic(self):
        """测试基本权重更新"""
        updater = TrustWeightUpdater(learning_rate=0.1)

        current_weights = {"agent_a": 1.0, "agent_b": 1.0}
        rewards = {"agent_a": 0.5, "agent_b": -0.5}

        new_weights = updater.update_weights(current_weights, rewards)

        assert new_weights["agent_a"] > 1.0  # 正向奖励增加
        assert new_weights["agent_b"] < 1.0  # 负向奖励减少

    def test_update_weights_clipped(self):
        """测试更新裁剪"""
        updater = TrustWeightUpdater(learning_rate=0.1, clip_param=0.1)

        current_weights = {"agent_a": 1.0}
        rewards = {"agent_a": 10.0}  # 极大的奖励

        new_weights = updater.update_weights(current_weights, rewards)

        # 应该被裁剪
        change = abs(new_weights["agent_a"] - 1.0)
        assert change <= 0.1 + 1e-9  # 不超过clip_param (考虑浮点精度)

    def test_update_weights_bounds(self):
        """测试权重边界"""
        updater = TrustWeightUpdater(learning_rate=0.1)

        current_weights = {"agent_a": 1.9}
        rewards = {"agent_a": 10.0}

        new_weights = updater.update_weights(current_weights, rewards)

        # 应该在边界内
        assert 0.0 <= new_weights["agent_a"] <= 2.0


class TestBackwardPropagation:
    """反向传播测试"""

    def test_propagate_feedback(self):
        """测试反馈传播"""
        bp = BackwardPropagation()

        user_feedback = {
            "satisfaction_score": 4,
            "feedback_items": []
        }

        layer_agents = {
            "convolution": ["conv_agent_1"],
            "code_generation": ["fc2_agent_1"]
        }

        result = bp.propagate_feedback(
            task_id="test-001",
            user_feedback=user_feedback,
            layer_agents=layer_agents,
            current_iteration=1
        )

        assert isinstance(result, dict)

    def test_calculate_layer_reward(self):
        """测试各层奖励计算"""
        bp = BackwardPropagation()

        reward = bp._calculate_layer_reward("code_generation", 1.0)

        assert reward > 0  # 代码生成层权重为0.8