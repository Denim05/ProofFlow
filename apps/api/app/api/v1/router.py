from fastapi import APIRouter
from app.api.v1.endpoints import cases, health

api_v1_router = APIRouter()

api_v1_router.include_router(cases.router)
api_v1_router.include_router(health.router)
