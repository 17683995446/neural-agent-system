"""
输出层API端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from app.core.logging import logger
from app.services.output.service import get_output_service

router = APIRouter(prefix="/output", tags=["Output Layer"])


class OutputRequest(BaseModel):
    task_id: str
    user_requirement: str
    fc1_output: Dict[str, Any]
    fc2_output: Dict[str, Any]
    fc3_output: Dict[str, Any]
    execution_time_ms: float


class OutputResponse(BaseModel):
    task_id: str
    layer: str
    document_path: str
    statistics: Dict[str, Any]


@router.post("/generate")
def generate_document(request: OutputRequest):
    """生成Markdown文档"""
    logger.info(f"Received output request for task {request.task_id}")

    try:
        service = get_output_service()
        result = service.process_task(
            request.task_id,
            request.user_requirement,
            request.fc1_output,
            request.fc2_output,
            request.fc3_output,
            request.execution_time_ms
        )
        return result
    except Exception as e:
        logger.error(f"Output generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))