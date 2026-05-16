"""
Agent核心单元 - 自定义NeuralAgent实现
实现双记忆体系集成、信任度管理

@deprecated: NeuralAgent当前未被实例化或继承。
  系统实际执行单元为各service层(service_fc1/service_fc2等)，
  通过neural_pipeline调度。此class保留供未来重构时
  将service层统一继承NeuralAgent以复用记忆/信任度逻辑。
"""
from typing import Any, Dict, List, Optional

from app.agents.memory.short_term import get_short_term_memory
from app.agents.memory.long_term import get_long_term_memory
from app.agents.trust.manager import get_trust_manager
from app.core.logging import logger


class NeuralAgent:
    """
    神经Agent - 系统最小执行单元
    集成双记忆体系与信任度管理的Agent基类
    """

    def __init__(
        self,
        agent_id: str,
        layer_name: str,
        role: str,
        goal: str,
        llm_config: Dict[str, Any],
        upper_layer_agents: Optional[List[str]] = None,
        **kwargs
    ):
        """
        初始化NeuralAgent

        Args:
            agent_id: Agent唯一标识
            layer_name: 所属层级名称
            role: Agent角色描述
            goal: Agent目标
            llm_config: LLM配置
            upper_layer_agents: 上层Agent列表（用于初始化信任度矩阵）
        """
        # 核心属性
        self.agent_id = agent_id
        self.layer_name = layer_name
        self.role = role
        self.goal = goal
        self.llm_config = llm_config
        self.system_message = f"你是{role}，你的目标是{goal}，严格按照固定JSON格式输出结果"

        # 获取信任度管理器
        self.trust_manager = get_trust_manager()

        # 初始化信任度矩阵
        if upper_layer_agents:
            self.trust_manager.initialize_trust_matrix(
                agent_id=agent_id,
                layer_name=layer_name,
                upper_layer_agents=upper_layer_agents
            )

        logger.info(f"Initialized NeuralAgent: {agent_id} (layer: {layer_name})")

    def process_message(
        self,
        messages: List[Dict[str, Any]],
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理消息 - 预处理 + 主处理 + 后处理
        """
        # 预处理：基于信任度过滤消息
        filtered_messages = messages
        if task_id:
            filtered_messages = self._pre_process(messages, task_id)

        # 主处理：子类实现
        response = self._do_process(filtered_messages)

        # 后处理：存储到记忆
        if task_id:
            self._post_process(response, task_id)

        return response

    def _pre_process(
        self,
        messages: List[Dict[str, Any]],
        task_id: str
    ) -> List[Dict[str, Any]]:
        """消息预处理 - 基于信任度过滤上层输入"""
        try:
            short_memory = get_short_term_memory(task_id)
            trust_matrix = short_memory.get_trust_matrix(self.agent_id)

            if not trust_matrix:
                return messages

            filtered_message = short_memory.filter_by_trust(messages, trust_matrix)

            logger.debug(
                f"Agent {self.agent_id} filtered messages: "
                f"{len(messages)} -> {len(filtered_message)}"
            )

            return filtered_message
        except Exception as e:
            logger.error(f"Error in _pre_process: {e}")
            return messages

    def _do_process(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """主处理逻辑 - 子类实现"""
        raise NotImplementedError("Subclass must implement _do_process")

    def _post_process(self, response: Dict[str, Any], task_id: str) -> None:
        """消息后处理 - 存储结果到记忆"""
        try:
            # 保存到短期记忆
            short_memory = get_short_term_memory(task_id)
            short_memory.save_message(self.agent_id, response)

            # 保存到长期记忆
            long_memory = get_long_term_memory(self.agent_id)
            long_memory.save_memory(
                content={
                    "layer": self.layer_name,
                    "message": response
                },
                metadata={
                    "type": "agent_output",
                    "task_id": task_id
                }
            )

            logger.debug(f"Agent {self.agent_id} saved output to memory")
        except Exception as e:
            logger.error(f"Error in _post_process: {e}")

    def set_task_context(self, task_id: str, context: Dict[str, Any]) -> bool:
        """设置任务上下文"""
        try:
            short_memory = get_short_term_memory(task_id)
            return short_memory.save_context(self.agent_id, context)
        except Exception as e:
            logger.error(f"Failed to set task context: {e}")
            return False

    def get_task_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务上下文"""
        try:
            short_memory = get_short_term_memory(task_id)
            return short_memory.get_context(self.agent_id)
        except Exception as e:
            logger.error(f"Failed to get task context: {e}")
            return None

    def get_similar_experiences(
        self,
        query: str,
        task_type: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """获取相似历史经验"""
        try:
            long_memory = get_long_term_memory(self.agent_id)
            return long_memory.get_similar_experiences(
                user_requirement=query,
                task_type=task_type,
                top_k=top_k
            )
        except Exception as e:
            logger.error(f"Failed to get similar experiences: {e}")
            return []

    def update_trust_weights(
        self,
        task_id: str,
        rewards: Dict[str, float],
        learning_rate: float = 0.1
    ) -> Dict[str, float]:
        """更新信任度权重"""
        try:
            return self.trust_manager.batch_adjust_trust(
                agent_id=self.agent_id,
                rewards=rewards,
                learning_rate=learning_rate
            )
        except Exception as e:
            logger.error(f"Failed to update trust weights: {e}")
            return {}

    def get_trust_statistics(self) -> Dict[str, Any]:
        """获取信任度统计"""
        return self.trust_manager.get_trust_statistics(self.agent_id)
