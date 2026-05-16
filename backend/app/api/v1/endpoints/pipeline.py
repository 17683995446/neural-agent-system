"""
神经网络Pipeline API端点 - 一键执行完整流程 + 迭代循环
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from uuid import uuid4

from app.core.logging import logger
from app.services.pipeline.neural_pipeline import get_neural_pipeline
from app.services.pipeline.iteration_manager import get_iteration_manager

router = APIRouter(prefix="/pipeline", tags=["Neural Pipeline"])


class PipelineExecuteRequest(BaseModel):
    task_id: Optional[str] = None
    user_requirement: str
    code_repo_url: Optional[str] = None
    local_code_path: Optional[str] = None
    target_branch: str = "main"
    max_iteration: int = 5


class PipelineExecuteResponse(BaseModel):
    task_id: str
    status: str
    layer_outputs: Dict[str, Any]
    execution_time_ms: float
    completed_at: str


class IterationStartRequest(BaseModel):
    """迭代式Pipeline启动请求"""
    task_id: Optional[str] = None
    user_requirement: str
    code_repo_url: Optional[str] = None
    local_code_path: Optional[str] = None
    target_branch: str = "main"
    max_iteration: int = 5


class IterationFeedbackRequest(BaseModel):
    """迭代反馈请求"""
    task_id: str
    satisfaction_score: float = 3.0
    stop_iteration: bool = False
    feedback_items: List[Dict[str, Any]] = []
    comments: Optional[str] = ""


@router.post("/execute", response_model=PipelineExecuteResponse)
def execute_pipeline(request: PipelineExecuteRequest):
    """
    一键执行完整的前向传播Pipeline（不迭代）
    从输入层到输出层的完整流程
    """
    task_id = request.task_id or str(uuid4())
    logger.info(f"[PIPELINE] Starting full pipeline execution for task {task_id}")

    try:
        pipeline = get_neural_pipeline()

        code_repo_path = request.local_code_path
        if not code_repo_path and request.code_repo_url:
            from app.services.input_layer.service import input_layer_service
            code_repo_path = input_layer_service.clone_or_copy_code_repo(
                repo_url=request.code_repo_url,
                local_path=None,
                task_id=task_id,
                target_branch=request.target_branch
            )

        if not code_repo_path:
            raise HTTPException(
                status_code=400,
                detail="Either code_repo_url or local_code_path must be provided"
            )

        result = pipeline.execute_forward_pipeline(
            task_id=task_id,
            user_requirement=request.user_requirement,
            code_repo_path=code_repo_path,
            max_iteration=request.max_iteration
        )

        return result

    except Exception as e:
        logger.error(f"[PIPELINE] Pipeline execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start-iteration")
def start_iterative_pipeline(request: IterationStartRequest):
    """
    启动迭代式Pipeline — 执行第1轮前向传播后等待用户反馈

    流程:
    1. 执行前向传播 (卷积→池化→FC1→FC2→FC3→输出)
    2. 返回结果 + status="awaiting_feedback"
    3. 用户通过 POST /api/v1/pipeline/feedback 提交反馈
    4. 系统执行反向传播，根据反馈决定继续或停止
    """
    task_id = request.task_id or str(uuid4())
    logger.info(f"[PIPELINE] Starting iterative pipeline for task {task_id}")

    try:
        pipeline = get_neural_pipeline()

        code_repo_path = request.local_code_path
        if not code_repo_path and request.code_repo_url:
            from app.services.input_layer.service import input_layer_service
            code_repo_path = input_layer_service.clone_or_copy_code_repo(
                repo_url=request.code_repo_url,
                local_path=None,
                task_id=task_id,
                target_branch=request.target_branch
            )

        if not code_repo_path:
            raise HTTPException(
                status_code=400,
                detail="Either code_repo_url or local_code_path must be provided"
            )

        result = pipeline.start_iterative_pipeline(
            task_id=task_id,
            user_requirement=request.user_requirement,
            code_repo_path=code_repo_path,
            max_iteration=request.max_iteration,
        )

        return result

    except Exception as e:
        logger.error(f"[PIPELINE] Iterative pipeline start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
def submit_iteration_feedback(request: IterationFeedbackRequest):
    """
    提交迭代反馈 — 系统执行反向传播后决定继续或停止

    反馈处理流程:
    1. 接收用户反馈 (satisfaction_score + stop_iteration标志)
    2. 执行反向传播，更新信任度权重
    3. 判断是否继续:
       - stop_iteration=true → 停止迭代
       - satisfaction_score >= 5 → 满意度满分，停止迭代
       - current_iteration >= max_iteration → 达到最大轮数，停止迭代
       - 否则 → 执行下一轮前向传播，继续等待反馈
    """
    logger.info(
        f"[PIPELINE] Received iteration feedback for task {request.task_id}, "
        f"satisfaction={request.satisfaction_score}, stop={request.stop_iteration}"
    )

    try:
        pipeline = get_neural_pipeline()

        feedback = {
            "satisfaction_score": request.satisfaction_score,
            "stop_iteration": request.stop_iteration,
            "feedback_items": request.feedback_items,
            "comments": request.comments or "",
        }

        result = pipeline.process_iteration_feedback(
            task_id=request.task_id,
            feedback=feedback,
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[PIPELINE] Feedback processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop/{task_id}")
def stop_iteration(task_id: str):
    """强制停止迭代"""
    try:
        pipeline = get_neural_pipeline()
        result = pipeline.stop_iteration(task_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[PIPELINE] Stop iteration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/iteration/{task_id}")
def get_iteration_status(task_id: str):
    """获取迭代状态"""
    try:
        pipeline = get_neural_pipeline()
        result = pipeline.get_iteration_status(task_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[PIPELINE] Get iteration status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/iterations")
def list_iterations():
    """列出所有迭代会话"""
    mgr = get_iteration_manager()
    return {"sessions": mgr.list_sessions()}


@router.post("/backward")
def execute_backward(
    task_id: str,
    user_feedback: Dict[str, Any]
):
    """
    执行反向传播Pipeline
    基于用户反馈更新信任度权重
    """
    logger.info(f"[PIPELINE] Starting backward propagation for task {task_id}")

    try:
        pipeline = get_neural_pipeline()
        result = pipeline.execute_backward_pipeline(task_id, user_feedback)
        return result
    except Exception as e:
        logger.error(f"[PIPELINE] Backward propagation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{task_id}")
def get_pipeline_status(task_id: str):
    """获取Pipeline执行状态"""
    from app.models.database import SessionLocal, TaskModel

    try:
        db = SessionLocal()
        task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
        db.close()

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return {
            "task_id": task_id,
            "status": task.status,
            "iteration_count": task.iteration_count,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pipeline status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
