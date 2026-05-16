"""
反向传播层服务 - 用户反馈迭代层
将用户反馈转化为误差信号，反向传递更新Agent信任度权重
LLM优先智能反馈分析，降级到数学公式计算
"""
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.agents.trust.backward import (
    RewardCalculator,
    TrustWeightUpdater,
    BackwardPropagation
)
from app.agents.trust.manager import get_trust_manager
from app.core.llm_client import create_llm_client
from app.core.logging import logger


class FeedbackProcessor:
    """反馈处理器"""

    @staticmethod
    def parse_feedback(feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析用户反馈"""
        return {
            "satisfaction_score": feedback_data.get("satisfaction_score", 3),
            "feedback_items": feedback_data.get("feedback_items", []),
            "comments": feedback_data.get("comments", ""),
            "iteration_number": feedback_data.get("iteration_number", 1)
        }


class BackwardPropagationService:
    """反向传播层服务"""

    def __init__(self):
        self.reward_calculator = RewardCalculator()
        self.weight_updater = TrustWeightUpdater()
        self.backward_propagation = BackwardPropagation()
        self.feedback_processor = FeedbackProcessor()
        self.llm_client = create_llm_client()

    def analyze_feedback_with_llm(
        self,
        user_feedback: Dict[str, Any],
        iteration: int
    ) -> Optional[Dict[str, Any]]:
        """LLM优先智能分析反馈，降级到公式计算"""
        if not self.llm_client.is_available:
            return None
        try:
            score = user_feedback.get("satisfaction_score", 3)
            comments = user_feedback.get("comments", "")
            items = user_feedback.get("feedback_items", [])

            prompt = f"""你是RL训练专家。分析用户反馈，给出奖励调整建议。

满意度(1-10): {score}
评语: {comments}
反馈项: {items}
迭代轮次: {iteration}

返回JSON: {{"reward": 0.0到1.0的奖励值, "layer_adjustments": {{"convolution": 0.0, "pooling": 0.0, "global_understanding": 0.0, "code_generation": 0.0, "test_generation": 0.0, "output": 0.0}}, "reasoning": "分析理由"}}
只返回JSON。"""
            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=1024
            )
            text = self.llm_client.get_response_text(response)
            if not text:
                return None
            from app.core.llm_utils import extract_json_from_llm_response
            result = extract_json_from_llm_response(text, fallback=None)
            if result and "reward" in result:
                logger.info(f"[LLM] Backward: feedback analyzed, reward={result['reward']:.4f}")
                return result
            return None
        except Exception as e:
            logger.warning(f"[LLM] Backward feedback analysis failed: {e}")
            return None

    def process_user_feedback(
        self,
        task_id: str,
        user_feedback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理用户反馈 - LLM优先分析，降级到公式计算"""
        start_time = time.time()
        logger.info(f"[START] Processing user feedback for task {task_id}")

        parsed = self.feedback_processor.parse_feedback(user_feedback)

        llm_analysis = self.analyze_feedback_with_llm(user_feedback, parsed.get("iteration_number", 1))
        if llm_analysis:
            reward = llm_analysis["reward"]
            logger.info(f"[TIMING] LLM reward: {reward:.3f}")
        else:
            reward = self.reward_calculator.calculate_reward(parsed)
            logger.info(f"[TIMING] Calculated reward: {reward:.3f}")

        layer_agents = self._get_layer_agents()
        updated_weights = self.backward_propagation.propagate_feedback(
            task_id=task_id,
            user_feedback=parsed,
            layer_agents=layer_agents,
            current_iteration=parsed["iteration_number"]
        )

        self._persist_trust_updates(task_id, updated_weights)

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[COMPLETE] Feedback processed in {elapsed:.2f}ms, {len(updated_weights)} weights updated")

        result = {
            "task_id": task_id,
            "layer": "backward_propagation",
            "reward": reward,
            "updated_weights": updated_weights,
            "feedback_summary": {
                "satisfaction_score": parsed["satisfaction_score"],
                "feedback_items_count": len(parsed["feedback_items"])
            },
            "processed_at": datetime.now().isoformat()
        }
        if llm_analysis:
            result["llm_reasoning"] = llm_analysis.get("reasoning", "")
        return result

    def _persist_trust_updates(self, task_id: str, updated_weights: Dict[str, Dict[str, float]]):
        """持久化信任度更新到DB+短期记忆+长期趋势"""
        trust_manager = get_trust_manager()

        for layer_name, weights in updated_weights.items():
            for agent_id, weight in weights.items():
                try:
                    trust_manager.adjust_trust(agent_id=agent_id, reward=weight - trust_manager.get_trust(agent_id))
                except Exception as e:
                    logger.debug("Trust DB update failed for %s/%s: %s", layer_name, agent_id, e)

        try:
            from app.agents.memory.short_term import ShortTermMemory
            for layer_name, weights in updated_weights.items():
                try:
                    stm = ShortTermMemory(task_id=task_id, agent_id=f"{layer_name}_agent")
                    stm.save_trust_matrix(f"{layer_name}_agent", weights)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            from app.agents.memory.long_term import get_long_term_memory
            ltm = get_long_term_memory()
            if ltm:
                ltm.update_trust_trend(task_id, updated_weights)
        except Exception:
            pass

        logger.info("Persisted trust updates for %d layers", len(updated_weights))

    def _get_layer_agents(self) -> Dict[str, List[str]]:
        """获取各层Agent映射"""
        return {
            "convolution": [f"conv_agent_{i}" for i in range(1, 6)],
            "pooling": ["pool_agent_1"],
            "global_understanding": ["fc1_agent"],
            "code_generation": [f"fc2_agent_{i}" for i in range(1, 4)],
            "test_generation": ["fc3_agent"],
            "output": ["output_agent"]
        }

    def calculate_layer_rewards(
        self,
        task_id: str,
        user_feedback: Dict[str, Any]
    ) -> Dict[str, float]:
        """计算各层奖励"""
        start_time = time.time()

        parsed = self.feedback_processor.parse_feedback(user_feedback)
        total_reward = self.reward_calculator.calculate_reward(parsed)

        layer_rewards = {
            "convolution": total_reward * 0.5,
            "pooling": total_reward * 0.6,
            "global_understanding": total_reward * 0.7,
            "code_generation": total_reward * 0.8,
            "test_generation": total_reward * 0.9,
            "output": total_reward * 1.0
        }

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Layer rewards calculated in {elapsed:.2f}ms")

        return layer_rewards

    def create_backward_output(
        self,
        task_id: str,
        user_feedback: Dict[str, Any],
        updated_weights: Dict[str, Dict[str, float]]
    ) -> Dict[str, Any]:
        """创建反向传播输出"""
        return {
            "task_id": task_id,
            "layer": "backward_propagation",
            "user_feedback": user_feedback,
            "updated_weights": updated_weights,
            "created_at": datetime.now().isoformat()
        }


# Singleton instance
_backward_service: Optional[BackwardPropagationService] = None


def get_backward_service() -> BackwardPropagationService:
    """获取反向传播服务实例"""
    global _backward_service
    if _backward_service is None:
        _backward_service = BackwardPropagationService()
    return _backward_service