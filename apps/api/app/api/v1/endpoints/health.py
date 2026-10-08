from fastapi import APIRouter, Response, status
from app.core.config import settings
from app.core.database import check_db_health
from app.schemas.health import HealthStatus

router = APIRouter()


@router.get("/health", response_model=HealthStatus)
async def get_health(response: Response):
    """Dynamic liveness and readiness probe inspecting database connection state."""
    db_health = await check_db_health()
    is_healthy = db_health["database"] == "connected"

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthStatus(
        status="healthy" if is_healthy else "degraded",
        database=db_health["database"],
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
    )
