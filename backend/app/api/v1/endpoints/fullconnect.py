"""
全连接层API端点 (FC1/FC2/FC3)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from app.core.logging import logger
from app.services.fullconnect import (
    get_global_understanding_service,
    get_code_generation_service,
    get_test_generation_service
)

router = APIRouter(prefix="/fullconnect", tags=["Full-connect Layers"])


# ==================== FC1 全局理解层 ====================
class FC1Request(BaseModel):
    task_id: str
    pooling_output: Dict[str, Any]
    user_requirement: str


@router.post("/fc1/process")
def process_fc1(request: FC1Request):
    """处理全局理解层"""
    logger.info(f"Received FC1 request for task {request.task_id}")

    try:
        service = get_global_understanding_service()
        result = service.process_task(
            request.task_id,
            request.pooling_output,
            request.user_requirement
        )
        return result
    except Exception as e:
        logger.error(f"FC1 processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FC2 代码生成层 ====================
class FC2Request(BaseModel):
    task_id: str
    fc1_output: Dict[str, Any]
    code_repo_path: str


@router.post("/fc2/process")
def process_fc2(request: FC2Request):
    """处理代码生成层"""
    logger.info(f"Received FC2 request for task {request.task_id}")

    try:
        service = get_code_generation_service()
        result = service.process_task(
            request.task_id,
            request.fc1_output,
            request.code_repo_path
        )
        return result
    except Exception as e:
        logger.error(f"FC2 processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FC3 测试生成层 ====================
class FC3Request(BaseModel):
    task_id: str
    fc2_output: Dict[str, Any]


@router.post("/fc3/process")
def process_fc3(request: FC3Request):
    """处理测试生成层"""
    logger.info(f"Received FC3 request for task {request.task_id}")

    try:
        service = get_test_generation_service()
        result = service.process_task(request.task_id, request.fc2_output)
        return result
    except Exception as e:
        logger.error(f"FC3 processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))