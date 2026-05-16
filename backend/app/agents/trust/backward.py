"""
基于Ray RLlib的信任度权重更新（反向传播核心）
"""
from typing import Any, Dict, List, Optional
import numpy as np

from app.core.config import settings
from app.core.logging import logger


class RewardCalculator:
    """奖励计算器 - 将用户反馈转化为可计算的奖励信号"""

    @staticmethod
    def calculate_reward(user_feedback: Dict[str, Any], task_result: Optional[Dict[str, Any]] = None) -> float:
        """
        计算奖励值，范围：[-1, 1]
        正向反馈：0~1，负向反馈：-1~0
        """
        # 1. 整体满意度评分（用户手动打分，0-5分）
        satisfaction_score = user_feedback.get("satisfaction_score", 3)
        # 映射到[-1, 1]: (score - 3) / 2
        # 3分 -> 0, 5分 -> 1, 0分 -> -1
        base_reward = (satisfaction_score - 3) / 2

        # 2. 具体反馈项的奖惩
        feedback_items = user_feedback.get("feedback_items", [])
        for feedback_item in feedback_items:
            feedback_type = feedback_item.get("type", "neutral")
            # 正向反馈（符合预期、效果好）+0.1
            if feedback_type == "positive":
                base_reward += 0.1
            # 负向反馈（不符合要求、有bug）-0.1
            elif feedback_type == "negative":
                base_reward -= 0.1
            # 中性反馈不加分也不减分
            elif feedback_type == "critical":
                # 关键问题 -0.2
                base_reward -= 0.2

        # 3. 限制奖励值范围
        return max(min(base_reward, 1.0), -1.0)

    @staticmethod
    def calculate_layer_reward(
        layer_name: str,
        layer_feedback: Dict[str, Any]
    ) -> float:
        """计算特定层的奖励值"""
        # 基于层类型调整奖励权重
        layer_weights = {
            "convolution": 1.0,
            "pooling": 1.0,
            "global_understanding": 1.2,
            "code_generation": 1.5,  # 代码生成层权重更高
            "test_generation": 1.3,
            "output": 1.0
        }

        base_reward = layer_feedback.get("layer_score", 0.0)
        weight = layer_weights.get(layer_name, 1.0)

        return base_reward * weight


class TrustWeightUpdater:
    """信任度权重更新器 - 基于PPO算法的信任度更新"""

    def __init__(self, learning_rate: float = 0.1, gamma: float = 0.99, clip_param: float = 0.2):
        self.learning_rate = learning_rate
        self.gamma = gamma  # 折扣因子
        self.clip_param = clip_param  # PPO裁剪参数
        self.trust_min = settings.trust_min_value
        self.trust_max = settings.trust_max_value

    def update_weights(
        self,
        current_weights: Dict[str, float],
        rewards: Dict[str, float],
        iteration: int = 0
    ) -> Dict[str, float]:
        """
        基于PPO思想更新信任度权重

        Args:
            current_weights: 当前信任度权重 {上层AgentID: 权重值}
            rewards: 各上层Agent的奖励信号 {上层AgentID: 奖励值}
            iteration: 当前迭代次数（用于学习率衰减）

        Returns:
            更新后的权重
        """
        # 动态学习率：随迭代次数衰减
        current_lr = self._get_adjusted_learning_rate(iteration)

        new_weights = {}
        for agent_id, current_weight in current_weights.items():
            reward = rewards.get(agent_id, 0.0)

            # PPO风格的更新：使用裁剪限制单次更新幅度
            raw_update = current_lr * reward

            # 裁剪更新幅度，避免单次变化过大
            clipped_update = np.clip(raw_update, -self.clip_param, self.clip_param)

            # 计算新权重
            new_weight = current_weight + clipped_update

            # 限制在有效范围内
            new_weight = np.clip(new_weight, self.trust_min, self.trust_max)

            new_weights[agent_id] = float(new_weight)

            logger.debug(
                f"Updated weight for {agent_id}: "
                f"{current_weight:.3f} -> {new_weights[agent_id]:.3f} "
                f"(reward={reward:.3f}, update={clipped_update:.3f})"
            )

        return new_weights

    def _get_adjusted_learning_rate(self, iteration: int) -> float:
        """计算调整后的学习率（随迭代次数衰减）"""
        # 简单衰减：learning_rate / (1 + iteration * 0.1)
        return self.learning_rate / (1 + iteration * 0.1)

    def compute_gradient(
        self,
        current_weights: Dict[str, float],
        rewards: Dict[str, float]
    ) -> Dict[str, float]:
        """计算权重更新的梯度（简化版）"""
        gradients = {}
        for agent_id, weight in current_weights.items():
            reward = rewards.get(agent_id, 0.0)
            # 简化的梯度：reward * learning_rate
            gradient = reward * self.learning_rate
            gradients[agent_id] = gradient
        return gradients


class BackwardPropagation:
    """反向传播控制器 - 协调各层的信任度权重更新"""

    def __init__(self):
        self.reward_calculator = RewardCalculator()
        self.weight_updater = TrustWeightUpdater(
            learning_rate=settings.default_learning_rate
        )

    def propagate_feedback(
        self,
        task_id: str,
        user_feedback: Dict[str, Any],
        layer_agents: Dict[str, List[str]],
        current_iteration: int
    ) -> Dict[str, Dict[str, float]]:
        """
        执行反向传播

        Args:
            task_id: 任务ID
            user_feedback: 用户反馈
            layer_agents: 各层的Agent映射 {层名: [AgentID列表]}
            current_iteration: 当前迭代次数

        Returns:
            各层更新后的信任度矩阵 {层名: {AgentID: 新权重}}
        """
        # 1. 计算整体奖励
        total_reward = self.reward_calculator.calculate_reward(user_feedback)

        logger.info(f"Starting backward propagation for task {task_id}")
        logger.info(f"Total reward: {total_reward:.3f}, iteration: {current_iteration}")

        # 2. 从输出层到输入层反向传播
        layer_names = [
            "output", "test_generation", "code_generation",
            "global_understanding", "pooling", "convolution"
        ]

        updated_weights = {}

        # 3. 逐层更新信任度
        for layer_name in layer_names:
            agents = layer_agents.get(layer_name, [])
            if not agents:
                continue

            # 计算该层的奖励（越靠近输出层，奖励越直接）
            layer_reward = self._calculate_layer_reward(layer_name, total_reward)

            # 更新该层所有Agent的信任度
            for agent_id in agents:
                rewards = {upper_id: layer_reward for upper_id in agents}

                try:
                    from app.agents.trust.manager import get_trust_manager
                    trust_mgr = get_trust_manager()
                    trust_matrix = trust_mgr.get_trust_matrix(agent_id, task_id)
                    current_weights = {
                        upper_id: trust_matrix.get(upper_id, 1.0)
                        for upper_id in agents
                    }
                except Exception as e:
                    logger.warning(f"Failed to load trust weights from DB, using defaults: {e}")
                    current_weights = {upper_id: 1.0 for upper_id in agents}

                new_weights = self.weight_updater.update_weights(
                    current_weights, rewards, current_iteration
                )

                updated_weights[agent_id] = new_weights

                logger.debug(f"Updated weights for {agent_id} in layer {layer_name}")

        logger.info(f"Backward propagation completed for task {task_id}")
        return updated_weights

    def _calculate_layer_reward(self, layer_name: str, total_reward: float) -> float:
        """计算特定层的奖励值"""
        # 各层对最终输出的贡献权重不同
        layer_contributions = {
            "output": 1.0,
            "test_generation": 0.9,
            "code_generation": 0.8,
            "global_understanding": 0.7,
            "pooling": 0.6,
            "convolution": 0.5
        }

        contribution = layer_contributions.get(layer_name, 0.5)
        return total_reward * contribution


# 单例实例
_backward_propagation: Optional[BackwardPropagation] = None


def get_backward_propagation() -> BackwardPropagation:
    """获取反向传播控制器实例"""
    global _backward_propagation
    if _backward_propagation is None:
        _backward_propagation = BackwardPropagation()
    return _backward_propagation