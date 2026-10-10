"""Tests for fail-closed development authentication and environment validation."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.dependencies import get_current_user_id
from app.main import app, lifespan


def test_dev_auth_bypass_default_is_false():
    """Default value of ALLOW_DEV_AUTH_BYPASS must strictly be False."""
    s = Settings(ENVIRONMENT="development")
    assert s.ALLOW_DEV_AUTH_BYPASS is False


@pytest.mark.parametrize("env", ["development", "test", "DEVELOPMENT", "Test"])
def test_dev_auth_bypass_permitted_in_allowed_environments(env: str):
    """ALLOW_DEV_AUTH_BYPASS=True is permitted in 'development' and 'test' environments."""
    s = Settings(ENVIRONMENT=env, ALLOW_DEV_AUTH_BYPASS=True)
    assert s.ALLOW_DEV_AUTH_BYPASS is True
    assert s.ENVIRONMENT.lower() in ("development", "test")


@pytest.mark.parametrize(
    "env",
    [
        "production",
        "staging",
        "preview",
        "qa",
        "unknown_env",
        "",
    ],
)
def test_dev_auth_bypass_forbidden_in_disallowed_environments(env: str):
    """ALLOW_DEV_AUTH_BYPASS=True must fail validation in staging, production, unset, or unknown environments."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT=env,
            ALLOW_DEV_AUTH_BYPASS=True,
            API_SECRET_KEY="test_key_long_enough_for_validation",
            MONGODB_URI="mongodb://user:pass@mongo.example.com:27017",
            CLERK_ISSUER="https://auth.example.com",
            CLERK_JWKS_URL="https://auth.example.com/.well-known/jwks.json",
        )
    err_str = str(exc_info.value).lower()
    assert "prohibits allow_dev_auth_bypass" in err_str or "allow_dev_auth_bypass is strictly prohibited" in err_str


@pytest.mark.asyncio
async def test_lifespan_fails_startup_if_bypass_enabled_in_forbidden_environment(monkeypatch):
    """FastAPI application lifespan must fail startup if ALLOW_DEV_AUTH_BYPASS is enabled in non-dev environment."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", True)

    with pytest.raises(RuntimeError) as exc_info:
        async with lifespan(app):
            pass

    assert "ALLOW_DEV_AUTH_BYPASS is strictly prohibited" in str(exc_info.value)


@pytest.mark.parametrize("env", ["production", "staging", "qa", "unknown", ""])
def test_get_current_user_id_requires_bearer_token_in_non_dev_environments(monkeypatch, env: str):
    """In non-dev/test environments, missing Bearer token must raise 401 even if X-User-ID is provided."""
    monkeypatch.setattr(settings, "ENVIRONMENT", env)
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=None, x_user_id="attacker_supplied_identity")

    assert exc_info.value.status_code == 401
    assert "Bearer token" in exc_info.value.detail


def test_get_current_user_id_permits_bypass_in_development_when_explicitly_enabled(monkeypatch):
    """In development with explicit ALLOW_DEV_AUTH_BYPASS=True, X-User-ID is resolved."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", True)

    resolved_user = get_current_user_id(authorization=None, x_user_id="legitimate_dev_tester")
    assert resolved_user == "legitimate_dev_tester"


def test_get_current_user_id_rejects_without_token_in_development_when_bypass_disabled(monkeypatch):
    """In development with ALLOW_DEV_AUTH_BYPASS=False, missing token must raise 401."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=None, x_user_id="dev_user")

    assert exc_info.value.status_code == 401
    assert "missing Bearer token" in exc_info.value.detail
