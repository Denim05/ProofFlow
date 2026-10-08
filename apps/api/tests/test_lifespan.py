from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app, lifespan


@pytest.mark.asyncio
async def test_root_endpoint():
    """Verify minimal root endpoint returns status, version, and service name."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "ProofFlow API"
        assert data["version"] == "0.1.0"
        assert data["status"] == "running"


@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown():
    """Verify FastAPI application lifespan invokes database connection on startup and cleanup on shutdown."""
    with patch("app.main.connect_to_mongo", new_callable=AsyncMock) as mock_connect, \
         patch("app.main.close_mongo_connection", new_callable=AsyncMock) as mock_close:
        async with lifespan(app):
            mock_connect.assert_awaited_once()
            mock_close.assert_not_awaited()

        mock_close.assert_awaited_once()
