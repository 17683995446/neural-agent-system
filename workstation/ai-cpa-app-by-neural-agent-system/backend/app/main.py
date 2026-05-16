from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, async_session
from app.services.init_data import init_data
from app.api.auth import router as auth_router
from app.api.questions import router as questions_router
from app.api.exam import router as exam_router
from app.api.ai import router as ai_router
from app.api.courses import router as courses_router
from app.api.orders import router as orders_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        try:
            await init_data(db)
        except Exception as e:
            print(f"Init data error: {e}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(questions_router, prefix="/api/v1")
app.include_router(exam_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(courses_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health")
async def health():
    return {"status": "ok"}
