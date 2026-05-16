"""
核心基础模块单元测试 — 信任度管理 (TrustManager + RewardCalculator + TrustWeightUpdater)
覆盖: 正常/边界/异常 — 初始化/更新/批量/过滤/统计/奖励/权重更新/DB降级
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.agents.trust.backward import RewardCalculator, TrustWeightUpdater, BackwardPropagation
from app.agents.trust.manager import TrustManager


class TestRewardCalculatorComprehensive:
    def test_satisfaction_3_is_zero(self):
        r = RewardCalculator.calculate_reward({"satisfaction_score": 3, "feedback_items": []})
        assert r == 0.0

    def test_satisfaction_5_max(self):
        r = RewardCalculator.calculate_reward({"satisfaction_score": 5, "feedback_items": []})
        assert r == 1.0

    def test_satisfaction_1_min(self):
        r = RewardCalculator.calculate_reward({"satisfaction_score": 1, "feedback_items": []})
        assert r == -1.0

    def test_positive_feedback_adds(self):
        r1 = RewardCalculator.calculate_reward({"satisfaction_score": 3, "feedback_items": []})
        r2 = RewardCalculator.calculate_reward({
            "satisfaction_score": 3,
            "feedback_items": [{"type": "positive"}]
        })
        assert r2 > r1

    def test_negative_feedback_subtracts(self):
        r1 = RewardCalculator.calculate_reward({"satisfaction_score": 3, "feedback_items": []})
        r2 = RewardCalculator.calculate_reward({
            "satisfaction_score": 3,
            "feedback_items": [{"type": "negative"}]
        })
        assert r2 < r1

    def test_critical_feedback_stronger(self):
        r_neg = RewardCalculator.calculate_reward({
            "satisfaction_score": 3,
            "feedback_items": [{"type": "negative"}]
        })
        r_crit = RewardCalculator.calculate_reward({
            "satisfaction_score": 3,
            "feedback_items": [{"type": "critical"}]
        })
        assert r_crit < r_neg

    def test_clamped_to_positive_one(self):
        r = RewardCalculator.calculate_reward({
            "satisfaction_score": 5,
            "feedback_items": [{"type": "positive"}] * 100
        })
        assert r <= 1.0

    def test_clamped_to_negative_one(self):
        r = RewardCalculator.calculate_reward({
            "satisfaction_score": 1,
            "feedback_items": [{"type": "critical"}] * 100
        })
        assert r >= -1.0

    def test_empty_feedback_items(self):
        r = RewardCalculator.calculate_reward({"satisfaction_score": 4})
        assert r == 0.5

    def test_missing_satisfaction_defaults_3(self):
        r = RewardCalculator.calculate_reward({"feedback_items": []})
        assert r == 0.0

    def test_layer_reward_weights(self):
        r_conv = RewardCalculator.calculate_layer_reward("convolution", {"layer_score": 1.0})
        r_fc2 = RewardCalculator.calculate_layer_reward("code_generation", {"layer_score": 1.0})
        assert r_fc2 > r_conv

    def test_layer_reward_unknown_layer(self):
        r = RewardCalculator.calculate_layer_reward("unknown_layer", {"layer_score": 1.0})
        assert r == 1.0


class TestTrustWeightUpdaterComprehensive:
    def test_positive_reward_increases_weight(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        new = updater.update_weights({"a": 1.0}, {"a": 0.5})
        assert new["a"] > 1.0

    def test_negative_reward_decreases_weight(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        new = updater.update_weights({"a": 1.0}, {"a": -0.5})
        assert new["a"] < 1.0

    def test_zero_reward_no_change(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        new = updater.update_weights({"a": 1.0}, {"a": 0.0})
        assert abs(new["a"] - 1.0) < 1e-9

    def test_weight_clipped_to_max(self):
        updater = TrustWeightUpdater(learning_rate=0.1, clip_param=10.0)
        new = updater.update_weights({"a": 1.95}, {"a": 100.0})
        assert new["a"] <= 2.0

    def test_weight_clipped_to_min(self):
        updater = TrustWeightUpdater(learning_rate=0.1, clip_param=10.0)
        new = updater.update_weights({"a": 0.05}, {"a": -100.0})
        assert new["a"] >= 0.0

    def test_clip_param_limits_update(self):
        updater = TrustWeightUpdater(learning_rate=1.0, clip_param=0.05)
        new = updater.update_weights({"a": 1.0}, {"a": 10.0})
        assert abs(new["a"] - 1.0) <= 0.05 + 1e-9

    def test_learning_rate_decay_with_iteration(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        lr0 = updater._get_adjusted_learning_rate(0)
        lr10 = updater._get_adjusted_learning_rate(10)
        assert lr10 < lr0

    def test_multiple_agents(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        weights = {"a": 1.0, "b": 1.0, "c": 1.0}
        rewards = {"a": 0.5, "b": 0.0, "c": -0.5}
        new = updater.update_weights(weights, rewards)
        assert new["a"] > new["b"] > new["c"]

    def test_missing_reward_defaults_zero(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        new = updater.update_weights({"a": 1.0}, {})
        assert abs(new["a"] - 1.0) < 1e-9

    def test_compute_gradient(self):
        updater = TrustWeightUpdater(learning_rate=0.1)
        grads = updater.compute_gradient({"a": 1.0}, {"a": 0.5})
        assert grads["a"] == 0.5 * 0.1


class TestTrustManagerMemoryOnly:
    def test_memory_only_get_returns_empty(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        result = mgr.get_trust_matrix("agent_x")
        assert result == {}

    def test_memory_only_update(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        ok = mgr.update_trust_matrix("agent_x", {"upper_a": 1.5})
        assert ok
        result = mgr.get_trust_matrix("agent_x")
        assert result == {"upper_a": 1.5}

    def test_filter_by_trust_threshold(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        mgr.update_trust_matrix("agent_x", {"a": 0.8, "b": 0.5, "c": 0.6})
        result = mgr.filter_by_trust_threshold("agent_x", threshold=0.6)
        assert "a" in result
        assert "b" not in result
        assert "c" in result

    def test_filter_by_trust_empty_matrix(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        result = mgr.filter_by_trust_threshold("agent_x", threshold=0.6)
        assert result == []

    def test_get_trust_statistics_empty(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        stats = mgr.get_trust_statistics("agent_x")
        assert stats["count"] == 0

    def test_get_trust_statistics_with_data(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        mgr.update_trust_matrix("agent_x", {"a": 0.5, "b": 1.5})
        stats = mgr.get_trust_statistics("agent_x")
        assert stats["count"] == 2
        assert stats["min"] == 0.5
        assert stats["max"] == 1.5
        assert abs(stats["mean"] - 1.0) < 1e-9

    def test_adjust_trust_by_feedback(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        mgr.update_trust_matrix("agent_x", {"upper_a": 1.0})
        result = mgr.adjust_trust_by_feedback("agent_x", "upper_a", reward=0.5, learning_rate=0.1)
        assert result["upper_a"] == pytest.approx(1.05)

    def test_adjust_trust_clamps_to_max(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        mgr.update_trust_matrix("agent_x", {"upper_a": 1.99})
        result = mgr.adjust_trust_by_feedback("agent_x", "upper_a", reward=10.0, learning_rate=1.0)
        assert result["upper_a"] <= mgr.max_value

    def test_batch_adjust_trust(self):
        mgr = TrustManager(db_session=None)
        mgr._db_available = False
        mgr.update_trust_matrix("agent_x", {"a": 1.0, "b": 1.0})
        result = mgr.batch_adjust_trust("agent_x", {"a": 0.5, "b": -0.5}, learning_rate=0.1)
        assert result["a"] > 1.0
        assert result["b"] < 1.0


class TestBackwardPropagationComprehensive:
    def test_calculate_layer_reward_contribution(self):
        bp = BackwardPropagation()
        r_output = bp._calculate_layer_reward("output", 1.0)
        r_conv = bp._calculate_layer_reward("convolution", 1.0)
        assert r_output > r_conv

    def test_calculate_layer_reward_unknown(self):
        bp = BackwardPropagation()
        r = bp._calculate_layer_reward("unknown", 1.0)
        assert r == 0.5

    def test_propagate_feedback_returns_dict(self):
        bp = BackwardPropagation()
        result = bp.propagate_feedback(
            task_id="t1",
            user_feedback={"satisfaction_score": 4, "feedback_items": []},
            layer_agents={"convolution": ["a1"]},
            current_iteration=0,
        )
        assert isinstance(result, dict)
