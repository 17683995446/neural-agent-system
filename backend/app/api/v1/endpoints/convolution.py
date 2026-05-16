"""
卷积层API端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.logging import logger
from app.services.convolution.service import get_convolution_service

router = APIRouter(prefix="/convolution", tags=["Convolution Layer"])


class ConvolutionRequest(BaseModel):
    """卷积层请求"""
    task_id: str
    code_repo_path: str
    granularity: Optional[str] = "file"
    max_agents: Optional[int] = 20


class ConvolutionResponse(BaseModel):
    """卷积层响应"""
    task_id: str
    layer: str
    total_files: int
    analyzed_files: List[Dict[str, Any]]
    failed_files: List[Dict[str, Any]]
    summary: Dict[str, Any]
    created_at: Optional[str] = None


@router.post("/process", response_model=ConvolutionResponse)
def process_convolution(request: ConvolutionRequest):
    """处理卷积层 - 分析代码文件"""
    logger.info(f"Received convolution request for task {request.task_id}")

    try:
        service = get_convolution_service()
        result = service.process_task(request.task_id, request.code_repo_path)
        return result
    except Exception as e:
        logger.error(f"Convolution processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files")
def get_code_files(task_id: str, code_repo_path: str):
    """获取代码文件列表"""
    try:
        service = get_convolution_service()
        files = service.get_code_files(code_repo_path)
        return {
            "task_id": task_id,
            "total_files": len(files),
            "files": files
        }
    except Exception as e:
        logger.error(f"Failed to get code files: {e}")
        raise HTTPException(status_code=500, detail=str(e))