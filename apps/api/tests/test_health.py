from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_healthy():
    """Verify /health returns 200 and connected status when database ping succeeds."""
    with patch("app.api.v1.endpoints.health.check_db_health", new_callable=AsyncMock) as mock_health:
        mock_health.return_value = {"status": "healthy", "database": "connected"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["database"] == "connected"
            assert data["service"] == "ProofFlow API"


@pytest.mark.asyncio
async def test_health_endpoint_degraded():
    """Verify /health returns 503 and degraded status when database is disconnected."""
    with patch("app.api.v1.endpoints.health.check_db_health", new_callable=AsyncMock) as mock_health:
        mock_health.return_value = {"status": "degraded", "database": "disconnected"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["database"] == "disconnected"
