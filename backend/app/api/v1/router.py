from fastapi import APIRouter

from app.api.v1.endpoints import input_layer
from app.api.v1.endpoints import convolution
from app.api.v1.endpoints import pooling
from app.api.v1.endpoints import fullconnect
from app.api.v1.endpoints import output
from app.api.v1.endpoints import backward
from app.api.v1.endpoints import pipeline

api_router = APIRouter()

api_router.include_router(input_layer.router)
api_router.include_router(convolution.router)
api_router.include_router(pooling.router)
api_router.include_router(fullconnect.router)
api_router.include_router(output.router)
api_router.include_router(backward.router)
api_router.include_router(pipeline.router)