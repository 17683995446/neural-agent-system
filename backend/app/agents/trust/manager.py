"""
信任度管理服务 - 基于Ray RLlib实现Agent信任度权重矩阵的更新和管理
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.database import SessionLocal, TrustModel


class TrustManager:
    """信任度管理器"""

    def __init__(self, db_session: Optional[Session] = None):
        self.db_session = db_session
        self.initial_value = settings.trust_initial_value
        self.min_value = settings.trust_min_value
        self.max_value = settings.trust_max_value
        self._memory_cache: Dict[str, Dict[str, float]] = {}
        self._db_available = True

    def _ensure_db_session(self):
        """确保数据库会话存在"""
        if self.db_session is None:
            self.db_session = SessionLocal()

    def get_trust_matrix(self, agent_id: str, task_id: Optional[str] = None) -> Dict[str, float]:
        """获取Agent的信任度矩阵"""
        cache_key = f"{agent_id}:{task_id or 'default'}"

        if not self._db_available:
            return self._memory_cache.get(cache_key, {})

        try:
            self._ensure_db_session()
            query = self.db_session.query(TrustModel).filter(TrustModel.agent_id == agent_id)
            if task_id:
                query = query.filter(TrustModel.task_id == task_id)

            result = query.first()
            if result:
                return result.trust_matrix
            return {}
        except Exception as e:
            logger.warning(f"DB unavailable, using memory cache: {e}")
            self._db_available = False
            self._memory_cache[cache_key] = self._memory_cache.get(cache_key, {})
            return self._memory_cache.get(cache_key, {})

    def initialize_trust_matrix(
        self,
        agent_id: str,
        layer_name: str,
        upper_layer_agents: List[str],
        task_id: Optional[str] = None
    ) -> Dict[str, float]:
        """初始化信任度矩阵"""
        trust_matrix = {
            upper_agent_id: self.initial_value
            for upper_agent_id in upper_layer_agents
        }

        try:
            self._ensure_db_session()
            existing = self.db_session.query(TrustModel).filter(
                TrustModel.agent_id == agent_id,
                TrustModel.layer_name == layer_name
            ).first()

            if existing:
                # 更新现有记录
                existing.trust_matrix = trust_matrix
                existing.update_time = datetime.now()
            else:
                # 创建新记录
                trust_record = TrustModel(
                    agent_id=agent_id,
                    layer_name=layer_name,
                    task_id=task_id,
                    trust_matrix=trust_matrix,
                    update_time=datetime.now()
                )
                self.db_session.add(trust_record)

            self.db_session.commit()
            logger.info(f"Initialized trust matrix for agent {agent_id}")
            return trust_matrix
        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Failed to initialize trust matrix: {e}")
            return {}

    def update_trust_matrix(
        self,
        agent_id: str,
        new_trust_matrix: Dict[str, float]
    ) -> bool:
        """更新信任度矩阵"""
        cache_key = f"{agent_id}:default"

        if not self._db_available:
            self._memory_cache[cache_key] = new_trust_matrix
            return True

        try:
            self._ensure_db_session()
            records = self.db_session.query(TrustModel).filter(
                TrustModel.agent_id == agent_id
            ).all()

            if not records:
                logger.warning(f"No trust record found for agent {agent_id}")
                return False

            for record in records:
                record.trust_matrix = new_trust_matrix
                record.update_time = datetime.now()

            self.db_session.commit()
            logger.info(f"Updated trust matrix for agent {agent_id}")
            return True
        except Exception as e:
            self.db_session.rollback()
            logger.warning(f"DB update failed, using memory cache: {e}")
            self._memory_cache[cache_key] = new_trust_matrix
            self._db_available = False
            return True

    def adjust_trust_by_feedback(
        self,
        agent_id: str,
        upper_agent_id: str,
        reward: float,
        learning_rate: float = 0.1
    ) -> Dict[str, float]:
        """基于用户反馈调整单个信任度权重"""
        current_matrix = self.get_trust_matrix(agent_id)
        current_value = current_matrix.get(upper_agent_id, self.initial_value)

        # 计算新的信任度: new = old + learning_rate * reward
        # reward范围: [-1, 1], learning_rate范围: [0.01, 0.5]
        new_value = current_value + learning_rate * reward

        # 限制在[min_value, max_value]范围内
        new_value = max(self.min_value, min(self.max_value, new_value))

        # 更新矩阵
        current_matrix[upper_agent_id] = new_value
        self.update_trust_matrix(agent_id, current_matrix)

        logger.info(
            f"Adjusted trust for agent {agent_id} -> {upper_agent_id}: "
            f"{current_value:.3f} -> {new_value:.3f} (reward={reward}, lr={learning_rate})"
        )

        return current_matrix

    def batch_adjust_trust(
        self,
        agent_id: str,
        rewards: Dict[str, float],
        learning_rate: float = 0.1
    ) -> Dict[str, float]:
        """批量调整信任度权重"""
        current_matrix = self.get_trust_matrix(agent_id)

        for upper_agent_id, reward in rewards.items():
            current_value = current_matrix.get(upper_agent_id, self.initial_value)
            new_value = current_value + learning_rate * reward
            new_value = max(self.min_value, min(self.max_value, new_value))
            current_matrix[upper_agent_id] = new_value

        self.update_trust_matrix(agent_id, current_matrix)

        logger.info(f"Batch adjusted trust for agent {agent_id}: {len(rewards)} updates")
        return current_matrix

    def filter_by_trust_threshold(
        self,
        agent_id: str,
        threshold: float = 0.6
    ) -> List[str]:
        """获取信任度高于阈值的上层Agent列表"""
        trust_matrix = self.get_trust_matrix(agent_id)
        return [
            upper_agent_id
            for upper_agent_id, score in trust_matrix.items()
            if score >= threshold
        ]

    def get_trust_statistics(self, agent_id: str) -> Dict[str, Any]:
        """获取信任度统计信息"""
        trust_matrix = self.get_trust_matrix(agent_id)

        if not trust_matrix:
            return {
                "agent_id": agent_id,
                "count": 0,
                "mean": 0.0,
                "min": 0.0,
                "max": 0.0
            }

        values = list(trust_matrix.values())
        return {
            "agent_id": agent_id,
            "count": len(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "distribution": trust_matrix
        }


# 单例实例
_trust_manager: Optional[TrustManager] = None


def get_trust_manager() -> TrustManager:
    """获取信任度管理器实例"""
    global _trust_manager
    if _trust_manager is None:
        _trust_manager = TrustManager()
    return _trust_manager