from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and graceful shutdown."""
    logger.info("ProofFlow API starting up...")

    # Fail-closed authentication check
    allowed_bypass_envs = {"development", "test"}
    env = (settings.ENVIRONMENT or "").strip().lower()
    if settings.ALLOW_DEV_AUTH_BYPASS and env not in allowed_bypass_envs:
        raise RuntimeError(
            f"Fatal application startup failure: ALLOW_DEV_AUTH_BYPASS is strictly prohibited in '{settings.ENVIRONMENT or 'unset'}' environment. "
            f"It is only permitted in {sorted(allowed_bypass_envs)}."
        )

    # Safe abandoned temporary file cleanup (files older than 1 hour)
    try:
        from app.services.storage import storage_service
        deleted_count = storage_service.cleanup_abandoned_temp_files(max_age_seconds=3600)
        if deleted_count > 0:
            logger.info("Cleaned up %d abandoned upload temporary file(s).", deleted_count)
    except Exception as exc:
        logger.warning("Temporary upload directory cleanup encountered an error during startup: %s", exc)

    await connect_to_mongo()
    try:
        yield
    finally:
        logger.info("ProofFlow API shutting down...")
        await close_mongo_connection()


app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Exception handlers for standard error envelope
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code_map = {
        404: "NOT_FOUND",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        429: "TOO_MANY_REQUESTS",
        503: "SERVICE_UNAVAILABLE",
    }
    error_code = code_map.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": error_code,
                "message": exc.detail,
                "details": [],
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        field_loc = " -> ".join(str(loc) for loc in err.get("loc", []) if loc != "body")
        details.append({
            "field": field_loc or "body",
            "issue": err.get("msg", "Invalid value"),
        })

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed",
                "details": details,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# Environment-driven CORS configuration
cors_origins = (
    settings.CORS_ORIGINS
    if isinstance(settings.CORS_ORIGINS, list)
    else [settings.CORS_ORIGINS]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Root-level health endpoint (GET /health)
app.include_router(health_router)

# Mount API v1 router (GET /api/v1/cases, POST /api/v1/cases, etc.)
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Minimal service status endpoint."""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "status": "running",
    }
