from fastapi import APIRouter
from app.api.v1.endpoints import cases, events, evidence, export, findings, health

api_v1_router = APIRouter()

api_v1_router.include_router(cases.router)
api_v1_router.include_router(evidence.router)
api_v1_router.include_router(events.router)
api_v1_router.include_router(findings.router)
api_v1_router.include_router(export.router)
api_v1_router.include_router(health.router)


