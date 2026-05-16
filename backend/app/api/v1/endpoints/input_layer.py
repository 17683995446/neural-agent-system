"""
输入层API端点 - 任务提交与查询
"""
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.database import get_db, TaskModel
from app.models.schemas import TaskInput, TaskOutput, TaskStatus
from app.services.input_layer.service import input_layer_service

router = APIRouter(prefix="/tasks", tags=["Input Layer"])


@router.post("/submit", response_model=TaskOutput)
async def submit_task(task_input: TaskInput, db: Session = Depends(get_db)):
    """
    提交任务 - 输入层的唯一入口
    接收用户需求与代码工程信息，初始化任务上下文
    """
    logger.info(f"Received task submission: {task_input.task_id}")

    # 如果未提供task_id，自动生成
    if not task_input.task_id:
        task_input.task_id = str(uuid4())

    try:
        # 初始化任务
        task_context = input_layer_service.initialize_task(task_input)

        # 返回任务信息
        return TaskOutput(
            task_id=task_context.task_id,
            status=TaskStatus.PENDING,
            md_document_path=None,
            created_at=task_context.created_at,
            updated_at=task_context.updated_at,
            iteration_count=0,
            user_satisfaction_score=None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@router.get("/{task_id}", response_model=TaskOutput)
async def get_task(task_id: str, db: Session = Depends(get_db)):
    """获取任务状态"""
    db_task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskOutput(
        task_id=db_task.task_id,
        status=TaskStatus(db_task.status),
        md_document_path=db_task.md_document_path,
        created_at=db_task.created_at,
        updated_at=db_task.updated_at,
        iteration_count=db_task.iteration_count,
        user_satisfaction_score=db_task.user_satisfaction_score
    )


@router.get("/", response_model=list[TaskOutput])
async def list_tasks(
    skip: int = 0,
    limit: int = 10,
    status: Optional[TaskStatus] = None,
    db: Session = Depends(get_db)
):
    """获取任务列表"""
    query = db.query(TaskModel)
    if status:
        query = query.filter(TaskModel.status == status.value)

    tasks = query.order_by(TaskModel.created_at.desc()).offset(skip).limit(limit).all()

    return [
        TaskOutput(
            task_id=task.task_id,
            status=TaskStatus(task.status),
            md_document_path=task.md_document_path,
            created_at=task.created_at,
            updated_at=task.updated_at,
            iteration_count=task.iteration_count,
            user_satisfaction_score=task.user_satisfaction_score
        )
        for task in tasks
    ]