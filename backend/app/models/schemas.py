from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ITERATING = "iterating"


class TaskInput(BaseModel):
    """输入层 - 任务输入模型"""
    task_id: str = Field(description="全局唯一任务ID，UUID格式")
    user_requirement: str = Field(description="用户的总需求描述")
    code_repo_url: Optional[HttpUrl] = Field(description="目标代码工程Git地址", default=None)
    local_code_path: Optional[str] = Field(description="本地代码工程路径", default=None)
    target_branch: str = Field(description="目标分支", default="main")
    max_iteration: int = Field(description="最大反馈迭代次数", default=5, ge=1, le=10)
    learning_rate: float = Field(description="学习率，信任度调整幅度", default=0.1, ge=0.01, le=0.5)
    llm_config: Dict[str, Any] = Field(description="LLM云API配置", default_factory=dict)


class TaskOutput(BaseModel):
    """任务输出模型"""
    task_id: str
    status: TaskStatus
    md_document_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    iteration_count: int = 0
    user_satisfaction_score: Optional[float] = None


class LayerInfo(BaseModel):
    """层级信息"""
    layer_name: str
    agent_id: str
    status: str
    confidence: float = 1.0


class TaskContext(BaseModel):
    """任务上下文"""
    task_id: str
    user_requirement: str
    code_repo_path: str
    target_branch: str
    max_iteration: int
    learning_rate: float
    llm_config: Dict[str, Any]
    current_iteration: int = 0
    layer_status: Dict[str, LayerInfo] = {}
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = {"extra": "ignore"}