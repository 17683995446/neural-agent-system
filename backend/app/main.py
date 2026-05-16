from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import logger
from app.models.database import init_db

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="类神经网络多Agent协作系统"
)

# CORS middleware
allowed_origins = [o.strip() for o in settings.allowed_cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    init_db()
    logger.info("Database initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    logger.info("Shutting down application")


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "version": settings.app_version}


@app.get("/health/detail")
async def health_detail():
    """详细健康检查 - 包含依赖状态"""
    from app.core.llm_client import get_llm_client
    checks = {}

    llm = get_llm_client()
    checks["llm"] = {"available": llm.is_available, "model": llm.model}

    try:
        from app.models.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = {"status": "connected"}
        finally:
            db.close()
    except Exception as e:
        checks["database"] = {"status": "unavailable", "error": str(e)[:100]}

    all_healthy = all(
        c.get("available", c.get("status") == "connected")
        for c in checks.values()
    )
    return {"status": "healthy" if all_healthy else "degraded", "checks": checks, "version": settings.app_version}