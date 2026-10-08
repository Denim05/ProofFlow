from unittest.mock import patch
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_create_case_success(client):
    """Verify successful case creation returns 201 with standard envelope and default PROCESSING status."""
    payload = {
        "title": "Refund Dispute - Damaged Headset",
        "description": "Customer claims item arrived shattered; merchant denies.",
        "tags": ["refund", "damaged"],
        "metadata": {"dispute_amount": 149.99},
    }
    response = await client.post("/api/v1/cases", json=payload, headers={"X-User-ID": "usr_alice"})
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    data = body["data"]
    assert data["case_id"].startswith("case_")
    assert data["user_id"] == "usr_alice"
    assert data["title"] == payload["title"]
    assert data["status"] == "PROCESSING"
    assert data["tags"] == ["refund", "damaged"]
    assert data["evidence_count"] == 0


@pytest.mark.asyncio
async def test_create_case_validation_error(client):
    """Verify malformed payload (short title) returns 422 with structured error details."""
    payload = {"title": "ab"}  # Min length is 3
    response = await client.post("/api/v1/cases", json=payload, headers={"X-User-ID": "usr_alice"})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert len(body["error"]["details"]) > 0


@pytest.mark.asyncio
async def test_get_existing_case(client):
    """Verify retrieving an existing case by ID returns 200 and matches created data."""
    create_res = await client.post(
        "/api/v1/cases",
        json={"title": "Dispute on Order #1001"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = create_res.json()["data"]["case_id"]

    get_res = await client.get(f"/api/v1/cases/{case_id}", headers={"X-User-ID": "usr_alice"})
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["success"] is True
    assert body["data"]["case_id"] == case_id
    assert body["data"]["user_id"] == "usr_alice"


@pytest.mark.asyncio
async def test_get_nonexistent_case(client):
    """Verify retrieving nonexistent case ID returns 404 with NOT_FOUND envelope."""
    response = await client.get("/api/v1/cases/case_nonexistent_999", headers={"X-User-ID": "usr_alice"})
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert "was not found" in body["error"]["message"]


@pytest.mark.asyncio
async def test_user_isolation(client):
    """Verify User B cannot access or list cases owned by User A."""
    res_a = await client.post(
        "/api/v1/cases",
        json={"title": "Alice Confidential Incident"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id_a = res_a.json()["data"]["case_id"]

    # Bob attempts to get Alice's case directly -> 404
    res_b_get = await client.get(f"/api/v1/cases/{case_id_a}", headers={"X-User-ID": "usr_bob"})
    assert res_b_get.status_code == 404

    # Bob lists cases -> should not see Alice's case
    res_b_list = await client.get("/api/v1/cases", headers={"X-User-ID": "usr_bob"})
    assert res_b_list.status_code == 200
    bob_items = res_b_list.json()["data"]["items"]
    assert len(bob_items) == 0


@pytest.mark.asyncio
async def test_list_cases_pagination_and_filtering(client):
    """Verify pagination calculation and status filtering on case listing."""
    await client.post(
        "/api/v1/cases",
        json={"title": "Case 1", "status": "PROCESSING"},
        headers={"X-User-ID": "usr_charlie"},
    )
    await client.post(
        "/api/v1/cases",
        json={"title": "Case 2"},
        headers={"X-User-ID": "usr_charlie"},
    )
    await client.post(
        "/api/v1/cases",
        json={"title": "Case 3"},
        headers={"X-User-ID": "usr_charlie"},
    )

    # Test list pagination (limit=2, page=1)
    res_page1 = await client.get("/api/v1/cases?page=1&limit=2", headers={"X-User-ID": "usr_charlie"})
    assert res_page1.status_code == 200
    data1 = res_page1.json()["data"]
    assert len(data1["items"]) == 2
    assert data1["pagination"]["total"] == 3
    assert data1["pagination"]["pages"] == 2
    assert data1["pagination"]["page"] == 1

    # Test page 2
    res_page2 = await client.get("/api/v1/cases?page=2&limit=2", headers={"X-User-ID": "usr_charlie"})
    data2 = res_page2.json()["data"]
    assert len(data2["items"]) == 1

    # Test status filter: PROCESSING
    res_filtered = await client.get("/api/v1/cases?status=PROCESSING", headers={"X-User-ID": "usr_charlie"})
    assert res_filtered.status_code == 200
    for item in res_filtered.json()["data"]["items"]:
        assert item["status"] == "PROCESSING"


@pytest.mark.asyncio
async def test_database_failure_handling():
    """Verify endpoint returns 503 when the database service is unavailable."""
    with patch("app.core.dependencies.get_database", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/cases", headers={"X-User-ID": "usr_alice"})
            assert response.status_code == 503
            body = response.json()
            assert body["success"] is False
            assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
