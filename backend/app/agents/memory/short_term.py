"""
短期记忆服务 - 基于Redis实现当前任务的上下文、层间交互消息、中间处理结果
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis

from app.core.config import settings
from app.core.logging import logger


class ShortTermMemory:
    """短期记忆 - 存储当前任务上下文"""

    def __init__(self, task_id: str, redis_client: Optional[redis.Redis] = None):
        self.task_id = task_id
        self.redis_client = redis_client or redis.from_url(
            settings.redis_url,
            decode_responses=True
        )
        self.ttl = 86400  # 24小时

    def _get_key(self, agent_id: str) -> str:
        """生成Redis Key"""
        return f"st:task:{self.task_id}:agent:{agent_id}"

    def save_message(self, agent_id: str, message: Dict[str, Any]) -> bool:
        """保存消息到短期记忆"""
        try:
            key = self._get_key(agent_id)
            message_data = {
                "message": json.dumps(message),
                "update_time": datetime.now().isoformat()
            }
            self.redis_client.hset(key, mapping=message_data)
            self.redis_client.expire(key, self.ttl)
            logger.debug(f"Saved message for agent {agent_id} in task {self.task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            return False

    def get_message(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取消息"""
        try:
            key = self._get_key(agent_id)
            data = self.redis_client.hgetall(key)
            if data and "message" in data:
                return json.loads(data["message"])
            return None
        except Exception as e:
            logger.error(f"Failed to get message: {e}")
            return None

    def save_trust_matrix(self, agent_id: str, trust_matrix: Dict[str, float]) -> bool:
        """保存信任度矩阵"""
        try:
            key = f"st:task:{self.task_id}:trust:{agent_id}"
            self.redis_client.set(
                key,
                json.dumps(trust_matrix),
                ex=self.ttl
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save trust matrix: {e}")
            return False

    def get_trust_matrix(self, agent_id: str) -> Dict[str, float]:
        """获取信任度矩阵"""
        try:
            key = f"st:task:{self.task_id}:trust:{agent_id}"
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
            # 返回默认信任度矩阵
            return {}
        except Exception as e:
            logger.error(f"Failed to get trust matrix: {e}")
            return {}

    def filter_by_trust(self, messages: List[Dict[str, Any]], trust_matrix: Dict[str, float]) -> List[Dict[str, Any]]:
        """基于信任度过滤消息"""
        if not trust_matrix:
            return messages

        filtered = []
        for msg in messages:
            sender_agent_id = msg.get("sender_agent_id", "")
            trust_score = trust_matrix.get(sender_agent_id, 1.0)
            if trust_score >= 0.6:
                filtered.append(msg)
        return filtered

    def save_context(self, agent_id: str, context: Dict[str, Any]) -> bool:
        """保存任务上下文"""
        try:
            key = f"st:task:{self.task_id}:context:{agent_id}"
            self.redis_client.set(
                key,
                json.dumps(context),
                ex=self.ttl
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save context: {e}")
            return False

    def get_context(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取任务上下文"""
        try:
            key = f"st:task:{self.task_id}:context:{agent_id}"
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get context: {e}")
            return None

    def clear(self, agent_id: Optional[str] = None) -> bool:
        """清空短期记忆"""
        try:
            if agent_id:
                # 清空指定Agent的记忆
                keys = [
                    self._get_key(agent_id),
                    f"st:task:{self.task_id}:trust:{agent_id}",
                    f"st:task:{self.task_id}:context:{agent_id}"
                ]
                self.redis_client.delete(*keys)
            else:
                # 清空整个任务的记忆
                pattern = f"st:task:{self.task_id}:*"
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Failed to clear memory: {e}")
            return False


def get_short_term_memory(task_id: str) -> ShortTermMemory:
    """获取短期记忆实例"""
    return ShortTermMemory(task_id)