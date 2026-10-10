from typing import Optional
from fastapi import Header, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase
from app.core.auth import verify_clerk_token
from app.core.config import settings
from app.core.database import get_database


def get_current_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> str:
    """Resolves the verified tenant user identifier with cryptographic token verification.

    Rules:
    1. If 'Authorization: Bearer <token>' is present:
       - Cryptographically verifies the RS256 token against Clerk JWKS.
       - Returns the verified subject claim ('sub').
       - Any supplied 'X-User-ID' header is strictly ignored and cannot override token identity.
    2. If 'Authorization' header is absent or does not contain a Bearer token:
       - Only permitted in explicitly configured 'development' or 'test' environments with ALLOW_DEV_AUTH_BYPASS=true.
       - In 'staging', 'production', an unset environment, or any unknown environment, strictly rejects with HTTP 401 Unauthorized.
    """
    allowed_bypass_envs = {"development", "test"}
    env = (settings.ENVIRONMENT or "").strip().lower()
    is_dev_or_test = env in allowed_bypass_envs

    if authorization and authorization.strip():
        auth_parts = authorization.strip().split(maxsplit=1)
        if len(auth_parts) != 2 or auth_parts[0].lower() != "bearer" or not auth_parts[1].strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header: expected format 'Bearer <token>'.",
            )
        token = auth_parts[1].strip()
        claims = verify_clerk_token(token)
        return claims["sub"]

    # No Bearer token provided
    if not is_dev_or_test:
        if env == "production":
            detail = "Production authentication required: missing Bearer token."
        else:
            detail = f"Authentication required: Bearer token is required in '{settings.ENVIRONMENT or 'unset'}' environment."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    # In development/test, check explicit bypass flag
    if settings.ALLOW_DEV_AUTH_BYPASS:
        return x_user_id.strip() if x_user_id and x_user_id.strip() else "dev_user_default"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: missing Bearer token. Set ALLOW_DEV_AUTH_BYPASS=true in development or test environment to enable development identity injection.",
    )


def get_db() -> AsyncDatabase:
    """Dependency that returns the active MongoDB database or raises 503 if disconnected."""
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )
    return db
