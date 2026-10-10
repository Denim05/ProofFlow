from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import FakeAsyncDatabase

MOCK_USER = "user_review_tester"
OTHER_USER = "user_other_tenant"


async def _create_test_case_with_finding(fake_db: FakeAsyncDatabase, user_id: str = MOCK_USER) -> tuple[str, str]:
    """Helper to create a case, evidence, and event that produces a deterministic finding."""
    case_id = f"case_test_{user_id}"
    evi_id = f"evi_{user_id}"

    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_id,
        "title": "Dispute Adjudication Case",
        "description": "Test Case for Human Review",
        "created_at": datetime.now(timezone.utc),
    })

    await fake_db.evidence.insert_one({
        "evidence_id": evi_id,
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": "invoice_unconfirmed.pdf",
        "active_processing_version": 1,
        "status": "READY",
        "created_at": datetime.now(timezone.utc),
    })

    await fake_db.events.insert_one({
        "event_id": f"evt_{user_id[:8]}",
        "case_id": case_id,
        "evidence_id": evi_id,
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": "REFUND_REQUESTED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Payment sent for order ORD-REVIEW-99",
        "char_start": 0,
        "char_end": 35,
        "order_reference": "ORD-REVIEW-99",
        "amount_currency": "USD",
        "amount_value": 450.00,
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "created_at": datetime.now(timezone.utc),
    })

    return case_id, evi_id


@pytest.mark.asyncio
async def test_review_valid_decision_types(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """1. Test each valid decision type: CONFIRMED_INCONSISTENCY, RESOLVED, DISMISSED."""
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)

    # Fetch computed finding
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert findings_res.status_code == 200
    findings = findings_res.json()["data"]["items"]
    assert len(findings) >= 1
    finding_id = findings[0]["finding_id"]

    # Decision: CONFIRMED_INCONSISTENCY
    res_confirm = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "CONFIRMED_INCONSISTENCY", "reason": "Verified genuine invoice discrepancy."},
        headers={"X-User-ID": MOCK_USER},
    )
    assert res_confirm.status_code == 200
    data_confirm = res_confirm.json()["data"]
    assert data_confirm["decision"] == "CONFIRMED_INCONSISTENCY"
    assert data_confirm["reviewer_id"] == MOCK_USER
    assert data_confirm["version"] == 1
    assert data_confirm["is_active"] is True

    # Decision: RESOLVED
    res_resolve = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "RESOLVED", "reason": "Settled with vendor directly."},
        headers={"X-User-ID": MOCK_USER},
    )
    assert res_resolve.status_code == 200
    data_resolve = res_resolve.json()["data"]
    assert data_resolve["decision"] == "RESOLVED"
    assert data_resolve["version"] == 2
    assert data_resolve["is_active"] is True

    # Decision: DISMISSED with mandatory reason
    res_dismiss = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "DISMISSED", "reason": "Expected partial payment terms per supplier contract."},
        headers={"X-User-ID": MOCK_USER},
    )
    assert res_dismiss.status_code == 200
    data_dismiss = res_dismiss.json()["data"]
    assert data_dismiss["decision"] == "DISMISSED"
    assert data_dismiss["version"] == 3
    assert data_dismiss["is_active"] is True


@pytest.mark.asyncio
async def test_dismissal_without_reason_rejected(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """2. Dismissal without a reason or with blank reason is rejected with 422."""
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    finding_id = findings_res.json()["data"]["items"][0]["finding_id"]

    # Missing reason
    res1 = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "DISMISSED"},
        headers={"X-User-ID": MOCK_USER},
    )
    assert res1.status_code == 422

    # Empty string reason
    res2 = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "DISMISSED", "reason": "   "},
        headers={"X-User-ID": MOCK_USER},
    )
    assert res2.status_code == 422

    # Too short reason
    res3 = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "DISMISSED", "reason": "no"},
        headers={"X-User-ID": MOCK_USER},
    )
    assert res3.status_code == 422


@pytest.mark.asyncio
async def test_invalid_decision_type_rejected(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """3. Invalid decision types are rejected with 422."""
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    finding_id = findings_res.json()["data"]["items"][0]["finding_id"]

    res = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "NOT_A_REAL_DECISION", "reason": "Some reason"},
        headers={"X-User-ID": MOCK_USER},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client: AsyncClient, fake_db: FakeAsyncDatabase, monkeypatch):
    """4. An unauthenticated request is rejected with 401 when dev bypass is off."""
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)

    res = await client.post(
        f"/api/v1/cases/{case_id}/findings/fnd_fake/review",
        json={"decision": "RESOLVED"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_tenant_isolation_cannot_adjudicate_other_user_case(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """5. A user cannot access or adjudicate another user's case or finding."""
    # Case belongs to MOCK_USER
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    finding_id = findings_res.json()["data"]["items"][0]["finding_id"]

    # OTHER_USER attempts to adjudicate
    res = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "RESOLVED"},
        headers={"X-User-ID": OTHER_USER},
    )
    # Returns 404 (not leaking the case's existence)
    assert res.status_code == 404

    # OTHER_USER attempts to list reviews
    res_list = await client.get(
        f"/api/v1/cases/{case_id}/reviews",
        headers={"X-User-ID": OTHER_USER},
    )
    assert res_list.status_code == 404


@pytest.mark.asyncio
async def test_finding_from_another_case_cannot_be_adjudicated(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """6. A finding from another case (or nonexistent finding) cannot be adjudicated."""
    case_id1, _ = await _create_test_case_with_finding(fake_db, f"{MOCK_USER}_1")
    case_id2, _ = await _create_test_case_with_finding(fake_db, f"{MOCK_USER}_2")

    # Fetch finding from case 2
    res2 = await client.get(f"/api/v1/cases/{case_id2}/findings", headers={"X-User-ID": f"{MOCK_USER}_2"})
    finding_id2 = res2.json()["data"]["items"][0]["finding_id"]

    # Attempt to adjudicate case 1 with finding_id from case 2
    res = await client.post(
        f"/api/v1/cases/{case_id1}/findings/{finding_id2}/review",
        json={"decision": "CONFIRMED_INCONSISTENCY"},
        headers={"X-User-ID": f"{MOCK_USER}_1"},
    )
    assert res.status_code == 404
    body = res.json()
    assert body["success"] is False
    assert "was not found in case" in body["error"]["message"]


@pytest.mark.asyncio
async def test_duplicate_submissions_handled_safely(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """7. Duplicate submissions and repeated retries are handled safely (idempotent, no duplicate active reviews)."""
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    finding_id = findings_res.json()["data"]["items"][0]["finding_id"]

    payload = {"decision": "RESOLVED", "reason": "Customer agreed to partial credit."}

    # First submission
    res1 = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json=payload,
        headers={"X-User-ID": MOCK_USER},
    )
    assert res1.status_code == 200
    rev1 = res1.json()["data"]

    # Second submission (identical retry)
    res2 = await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json=payload,
        headers={"X-User-ID": MOCK_USER},
    )
    assert res2.status_code == 200
    rev2 = res2.json()["data"]

    # Idempotent: exact same review ID and version
    assert rev1["review_id"] == rev2["review_id"]
    assert rev1["version"] == rev2["version"]

    # Verify only ONE active record exists in database
    active_count = await fake_db.finding_reviews.count_documents({
        "case_id": case_id,
        "finding_id": finding_id,
        "is_active": True,
    })
    assert active_count == 1


@pytest.mark.asyncio
async def test_review_history_preserved_after_decision_changes(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """8. Review history is preserved when decision changes."""
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    finding_id = findings_res.json()["data"]["items"][0]["finding_id"]

    # Decision 1
    await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "CONFIRMED_INCONSISTENCY", "reason": "Under initial investigation."},
        headers={"X-User-ID": MOCK_USER},
    )

    # Decision 2: Changed to RESOLVED
    await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "RESOLVED", "reason": "Resolved after bank confirmation."},
        headers={"X-User-ID": MOCK_USER},
    )

    # Retrieve history
    history_res = await client.get(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/reviews",
        headers={"X-User-ID": MOCK_USER},
    )
    assert history_res.status_code == 200
    history = history_res.json()["data"]["items"]
    assert len(history) == 2

    # Latest decision (version 2) is active
    assert history[0]["version"] == 2
    assert history[0]["decision"] == "RESOLVED"
    assert history[0]["is_active"] is True

    # Earlier decision (version 1) is preserved in audit history as inactive
    assert history[1]["version"] == 1
    assert history[1]["decision"] == "CONFIRMED_INCONSISTENCY"
    assert history[1]["is_active"] is False


@pytest.mark.asyncio
async def test_finding_regeneration_preserves_review_and_active_review_attached(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """9. Finding regeneration does not silently erase review history; active review is attached."""
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    finding_id = findings_res.json()["data"]["items"][0]["finding_id"]

    # Adjudicate finding
    await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "RESOLVED", "reason": "Payment confirmed in ERP."},
        headers={"X-User-ID": MOCK_USER},
    )

    # Re-fetch findings (simulating recomputation)
    refetched = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert refetched.status_code == 200
    item = refetched.json()["data"]["items"][0]

    # Verify active review is attached directly to finding response
    assert item["active_review"] is not None
    assert item["active_review"]["decision"] == "RESOLVED"
    assert item["active_review"]["reason"] == "Payment confirmed in ERP."

    # Verify ML model confidence score was NOT mutated
    assert item["model_confidence"] == 0.9


@pytest.mark.asyncio
async def test_list_case_reviews(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """10. Listing case reviews returns active records."""
    case_id, _ = await _create_test_case_with_finding(fake_db, MOCK_USER)
    findings_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    finding_id = findings_res.json()["data"]["items"][0]["finding_id"]

    await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "CONFIRMED_INCONSISTENCY", "reason": "Confirmed discrepancy."},
        headers={"X-User-ID": MOCK_USER},
    )

    reviews_res = await client.get(f"/api/v1/cases/{case_id}/reviews", headers={"X-User-ID": MOCK_USER})
    assert reviews_res.status_code == 200
    rev_items = reviews_res.json()["data"]["items"]
    assert len(rev_items) == 1
    assert rev_items[0]["finding_id"] == finding_id
    assert rev_items[0]["decision"] == "CONFIRMED_INCONSISTENCY"
