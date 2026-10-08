from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.core import database


@pytest.mark.asyncio
async def test_db_health_when_client_is_none():
    """Verify check_db_health reports degraded when no client exists."""
    with patch.object(database, "_client", None):
        health = await database.check_db_health()
        assert health["status"] == "degraded"
        assert health["database"] == "disconnected"


@pytest.mark.asyncio
async def test_db_health_when_ping_succeeds():
    """Verify check_db_health reports healthy when MongoDB responds to ping."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})

    with patch.object(database, "_client", mock_client):
        health = await database.check_db_health()
        assert health["status"] == "healthy"
        assert health["database"] == "connected"
        mock_client.admin.command.assert_awaited_once_with("ping")


@pytest.mark.asyncio
async def test_db_health_when_ping_fails():
    """Verify check_db_health reports degraded when MongoDB ping raises an exception."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=Exception("Connection timeout"))

    with patch.object(database, "_client", mock_client):
        health = await database.check_db_health()
        assert health["status"] == "degraded"
        assert health["database"] == "disconnected"


@pytest.mark.asyncio
async def test_init_db_indexes():
    """Verify init_db_indexes establishes the 3 approved indexes with exact parameters."""
    mock_db = MagicMock()
    mock_cases = MagicMock()
    mock_cases.create_index = AsyncMock()
    mock_db.cases = mock_cases

    await database.init_db_indexes(mock_db)

    assert mock_cases.create_index.await_count == 3
    created_index_names = [
        call.kwargs.get("name") for call in mock_cases.create_index.await_args_list
    ]
    assert "idx_cases_case_id_unique" in created_index_names
    assert "idx_cases_user_created" in created_index_names
    assert "idx_cases_user_status_created" in created_index_names


@pytest.mark.asyncio
async def test_close_mongo_connection():
    """Verify close_mongo_connection properly closes and clears client references."""
    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    database._client = mock_client
    database._db = MagicMock()

    await database.close_mongo_connection()

    mock_client.close.assert_awaited_once()
    assert database.get_client() is None
    assert database.get_database() is None
