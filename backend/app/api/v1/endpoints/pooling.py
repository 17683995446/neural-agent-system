"""
池化层API端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.core.logging import logger
from app.services.pooling.service import get_pooling_service

router = APIRouter(prefix="/pooling", tags=["Pooling Layer"])


class PoolingRequest(BaseModel):
    """池化层请求"""
    task_id: str
    convolution_output: Dict[str, Any]
    user_requirement: str


class PoolingResponse(BaseModel):
    """池化层响应"""
    task_id: str
    layer: str
    compressed_features: List[Dict[str, Any]]
    global_features: Dict[str, Any]
    total_files_processed: int
    created_at: Optional[str] = None


@router.post("/process", response_model=PoolingResponse)
def process_pooling(request: PoolingRequest):
    """处理池化层 - 压缩特征"""
    logger.info(f"Received pooling request for task {request.task_id}")

    try:
        service = get_pooling_service()
        result = service.process_task(
            request.task_id,
            request.convolution_output,
            request.user_requirement
        )
        return result
    except Exception as e:
        logger.error(f"Pooling processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compress")
def compress_features(
    task_id: str,
    analysis_results: List[Dict[str, Any]],
    user_requirement: str
):
    """压缩特征接口"""
    try:
        service = get_pooling_service()
        compressed = service.compress_features(analysis_results, user_requirement)
        return {
            "task_id": task_id,
            "original_count": len(analysis_results),
            "compressed_count": len(compressed),
            "compressed_features": compressed
        }
    except Exception as e:
        logger.error(f"Compression failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))