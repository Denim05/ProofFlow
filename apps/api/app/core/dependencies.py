from typing import Optional
from fastapi import Header, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import settings
from app.core.database import get_database


def get_current_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> str:
    """Resolves the tenant user identifier with strict environment isolation.

    In development/testing environments, supports 'X-User-ID' header injection
    or falls back to 'dev_user_default' for local ergonomics.
    In production environments, strictly rejects unauthenticated requests and
    requires a valid user identity.
    """
    if settings.ENVIRONMENT.lower() == "production":
        if not x_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: missing user identity",
            )
        return x_user_id

    # Non-production development / test fallback
    return x_user_id.strip() if x_user_id and x_user_id.strip() else "dev_user_default"


def get_db() -> AsyncDatabase:
    """Dependency that returns the active MongoDB database or raises 503 if disconnected."""
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )
    return db
