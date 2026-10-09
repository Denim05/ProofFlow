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
    """Verify init_db_indexes establishes approved indexes across cases, evidence, and events."""
    mock_db = MagicMock()
    mock_cases = MagicMock()
    mock_cases.create_index = AsyncMock()
    mock_evidence = MagicMock()
    mock_evidence.create_index = AsyncMock()
    mock_events = MagicMock()
    mock_events.create_index = AsyncMock()

    mock_db.cases = mock_cases
    mock_db.evidence = mock_evidence
    mock_db.events = mock_events

    await database.init_db_indexes(mock_db)

    assert mock_cases.create_index.await_count == 3
    cases_indexes = [call.kwargs.get("name") for call in mock_cases.create_index.await_args_list]
    assert "idx_cases_case_id_unique" in cases_indexes
    assert "idx_cases_user_created" in cases_indexes
    assert "idx_cases_user_status_created" in cases_indexes

    assert mock_evidence.create_index.await_count == 4
    evidence_indexes = [call.kwargs.get("name") for call in mock_evidence.create_index.await_args_list]
    assert "idx_evidence_evidence_id_unique" in evidence_indexes
    assert "idx_evidence_case_sha256_unique" in evidence_indexes

    assert mock_events.create_index.await_count == 7
    events_indexes = [call.kwargs.get("name") for call in mock_events.create_index.await_args_list]
    assert "idx_events_event_id_unique" in events_indexes
    assert "idx_events_evidence_version" in events_indexes
    assert "idx_events_evidence_run" in events_indexes


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
