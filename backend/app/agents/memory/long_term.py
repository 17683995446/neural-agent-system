"""
长期记忆服务 - 基于Milvus/Chroma实现Agent历史任务经验、信任度趋势存储
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_community.vectorstores import Milvus, Chroma
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.core.logging import logger

# 全局向量存储实例
_vector_store = None
_vector_store_initialized = False
_use_chroma = False


def get_embeddings():
    """获取嵌入模型"""
    return OpenAIEmbeddings(
        model="text-embedding-3-large",
        api_key=settings.anthropic_auth_token or settings.openai_api_key
    )


def get_vector_store():
    """获取向量存储实例"""
    global _vector_store, _vector_store_initialized, _use_chroma

    if _vector_store_initialized:
        return _vector_store

    _vector_store_initialized = True

    try:
        _vector_store = Milvus(
            embedding_function=get_embeddings(),
            connection_args={"host": "localhost", "port": "19530"},
            collection_name="agent_memories"
        )
        logger.info("Connected to Milvus vector store")
    except Exception as e:
        logger.warning(f"Failed to connect to Milvus: {e}, falling back to Chroma")
        try:
            _vector_store = Chroma(
                embedding_function=get_embeddings(),
                collection_name="agent_memories"
            )
            _use_chroma = True
            logger.info("Using Chroma vector store")
        except Exception as e2:
            logger.error(f"Failed to initialize vector store: {e2}")
            _vector_store = None

    return _vector_store


class LongTermMemory:
    """长期记忆 - 存储Agent历史任务经验、信任度趋势"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.vector_store = get_vector_store()

    def save_memory(
        self,
        content: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> bool:
        """保存记忆到向量数据库"""
        if not self.vector_store:
            logger.warning("Vector store not available, skipping memory save")
            return False

        try:
            # 构建文本内容
            content_text = json.dumps(content)

            # 构建元数据
            meta = {
                "agent_id": self.agent_id,
                "create_time": datetime.now().isoformat(),
                **metadata
            }

            # 添加到向量存储
            self.vector_store.add_texts(
                texts=[content_text],
                metadatas=[meta]
            )

            logger.debug(f"Saved memory for agent {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            return False

    def retrieve_similar(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.8,
        task_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """检索相似历史记忆"""
        if not self.vector_store:
            logger.warning("Vector store not available")
            return []

        try:
            # 构建过滤条件
            filter_dict = {"agent_id": self.agent_id}
            if task_type:
                filter_dict["task_type"] = task_type

            # 执行相似度搜索
            docs_with_scores = self.vector_store.similarity_search_with_score(
                query=query,
                k=top_k,
                filter=filter_dict
            )

            # 过滤低相似度结果
            results = []
            for doc, score in docs_with_scores:
                # 将距离转换为相似度 (距离越小相似度越高)
                similarity = 1 / (1 + score)
                if similarity >= threshold:
                    results.append({
                        "content": json.loads(doc.page_content),
                        "metadata": doc.metadata,
                        "similarity": similarity
                    })

            logger.debug(f"Retrieved {len(results)} similar memories for agent {self.agent_id}")
            return results
        except Exception as e:
            logger.error(f"Failed to retrieve similar memories: {e}")
            return []

    def update_trust_trend(
        self,
        task_id: str,
        trust_matrix: Dict[str, float]
    ) -> bool:
        """更新Agent信任度趋势"""
        return self.save_memory(
            content={"trust_matrix": trust_matrix},
            metadata={
                "type": "trust_trend",
                "task_id": task_id
            }
        )

    def get_trust_trend(
        self,
        task_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取信任度趋势"""
        if not self.vector_store:
            return []

        try:
            filter_dict = {
                "agent_id": self.agent_id,
                "type": "trust_trend"
            }
            if task_id:
                filter_dict["task_id"] = task_id

            docs = self.vector_store.get(
                where=filter_dict,
                limit=limit
            )

            results = []
            for doc in docs:
                results.append({
                    "content": json.loads(doc.page_content),
                    "metadata": doc.metadata
                })

            return results
        except Exception as e:
            logger.error(f"Failed to get trust trend: {e}")
            return []

    def save_task_experience(
        self,
        task_id: str,
        task_type: str,
        user_requirement: str,
        result: Dict[str, Any],
        user_feedback: Optional[Dict[str, Any]] = None
    ) -> bool:
        """保存任务执行经验"""
        content = {
            "task_id": task_id,
            "task_type": task_type,
            "user_requirement": user_requirement,
            "result": result,
            "user_feedback": user_feedback
        }

        return self.save_memory(
            content=content,
            metadata={
                "type": "task_experience",
                "task_type": task_type,
                "task_id": task_id
            }
        )

    def get_similar_experiences(
        self,
        user_requirement: str,
        task_type: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """获取相似任务执行经验"""
        return self.retrieve_similar(
            query=user_requirement,
            top_k=top_k,
            threshold=0.7,  # 经验相似度阈值稍低
            task_type=task_type
        )


def get_long_term_memory(agent_id: str) -> LongTermMemory:
    """获取长期记忆实例"""
    return LongTermMemory(agent_id)