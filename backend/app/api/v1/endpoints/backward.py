"""
反向传播层API端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from app.core.logging import logger
from app.services.backward.service import get_backward_service

router = APIRouter(prefix="/backward", tags=["Backward Propagation"])


class FeedbackItem(BaseModel):
    type: str
    description: str


class UserFeedbackRequest(BaseModel):
    task_id: str
    satisfaction_score: float = 3.0
    feedback_items: List[FeedbackItem] = []
    comments: Optional[str] = ""
    iteration_number: int = 1


class BackwardResponse(BaseModel):
    task_id: str
    layer: str
    reward: float
    updated_weights: Dict[str, Dict[str, float]]
    feedback_summary: Dict[str, Any]


@router.post("/feedback", response_model=BackwardResponse)
def process_feedback(request: UserFeedbackRequest):
    """处理用户反馈，执行反向传播"""
    logger.info(f"Received feedback for task {request.task_id}")

    try:
        service = get_backward_service()
        result = service.process_user_feedback(
            request.task_id,
            request.model_dump()
        )
        return result
    except Exception as e:
        logger.error(f"Backward processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate-rewards")
def calculate_rewards(
    task_id: str,
    user_feedback: Dict[str, Any]
):
    """计算各层奖励"""
    try:
        service = get_backward_service()
        rewards = service.calculate_layer_rewards(task_id, user_feedback)
        return {
            "task_id": task_id,
            "layer_rewards": rewards
        }
    except Exception as e:
        logger.error(f"Reward calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))