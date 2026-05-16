from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

from app.core.config import settings

Base = declarative_base()


class TaskModel(Base):
    """任务数据库模型"""
    __tablename__ = "tasks"

    task_id = Column(String(64), primary_key=True, index=True)
    user_requirement = Column(Text, nullable=False)
    code_repo_url = Column(String(512), nullable=True)
    local_code_path = Column(String(512), nullable=True)
    target_branch = Column(String(64), default="main")
    max_iteration = Column(Integer, default=5)
    learning_rate = Column(Float, default=0.1)
    llm_config = Column(JSON, default=dict)
    status = Column(String(32), default="pending")
    md_document_path = Column(String(512), nullable=True)
    iteration_count = Column(Integer, default=0)
    user_satisfaction_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TrustModel(Base):
    """信任度权重数据库模型"""
    __tablename__ = "trust_weights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    layer_name = Column(String(32), nullable=False)
    task_id = Column(String(64), nullable=True, index=True)
    trust_matrix = Column(JSON, default=dict)  # {上层AgentID: 信任度分数}
    update_time = Column(DateTime, default=datetime.now)


class AgentMemoryModel(Base):
    """Agent记忆数据库模型"""
    __tablename__ = "agent_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=True, index=True)
    memory_type = Column(String(32), nullable=False)  # short_term / long_term
    content = Column(Text, nullable=False)
    memory_metadata = Column(JSON, default=dict)
    create_time = Column(DateTime, default=datetime.now)


# Database engine and session
engine = create_engine(settings.postgres_url, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库表"""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Database initialization skipped (DB unavailable): {e}")


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()