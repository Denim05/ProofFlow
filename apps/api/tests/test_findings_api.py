from datetime import datetime, timezone
from decimal import Decimal
from bson import Decimal128
import pytest
from httpx import AsyncClient

from tests.conftest import FakeAsyncDatabase

MOCK_USER = "dev-user"
OTHER_USER = "intruder-user"


async def setup_case(fake_db: FakeAsyncDatabase, case_id: str, user_id: str = MOCK_USER):
    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_id,
        "title": "Dispute Case",
        "description": "Test case for findings reasoning",
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })


async def setup_evidence(
    fake_db: FakeAsyncDatabase,
    case_id: str,
    evidence_id: str,
    filename: str,
    active_version: int = 1,
    status: str = "READY",
    user_id: str = MOCK_USER,
):
    await fake_db.evidence.insert_one({
        "evidence_id": evidence_id,
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": filename,
        "media_type": "application/pdf",
        "file_size_bytes": 1000,
        "sha256_hash": "a" * 64,
        "status": status,
        "processing_version": active_version,
        "active_processing_version": active_version,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })


@pytest.mark.asyncio
async def test_empty_case_findings(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Case with no evidence returns 0 findings."""
    case_id = "case_empty"
    await setup_case(fake_db, case_id)

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["case_id"] == case_id
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_case_ownership_enforcement(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Unauthorized user receives 404 when querying another user's case findings."""
    case_id = "case_private"
    await setup_case(fake_db, case_id, user_id=MOCK_USER)

    # Intruder request
    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": OTHER_USER})
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert "not found" in body["error"]["message"].lower()

    # Non-existent case
    resp_none = await client.get("/api/v1/cases/case_nonexistent/findings", headers={"X-User-Id": MOCK_USER})
    assert resp_none.status_code == 404
    body_none = resp_none.json()
    assert body_none["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_active_version_filtering_superseded_excluded(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Superseded processing versions are ignored; only active versions generate findings."""
    case_id = "case_versioned"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_1", "order.pdf", active_version=2)
    await setup_evidence(fake_db, case_id, "evi_2", "invoice.pdf", active_version=1)

    # Stale event in evi_1 from superseded version 1
    await fake_db.events.insert_one({
        "event_id": "evt_old_1",
        "case_id": case_id,
        "evidence_id": "evi_1",
        "user_id": MOCK_USER,
        "processing_version": 1,  # superseded
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Old order PO-123 for $5,000",
        "char_start": 0,
        "char_end": 28,
        "order_reference": "PO-123",
        "amount_currency": "USD",
        "amount_value": Decimal("5000.00"),
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "created_at": datetime.now(timezone.utc),
    })

    # Active event in evi_2
    await fake_db.events.insert_one({
        "event_id": "evt_act_2",
        "case_id": case_id,
        "evidence_id": "evi_2",
        "user_id": MOCK_USER,
        "processing_version": 1,
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Invoice for PO-123 for $9,000",
        "char_start": 0,
        "char_end": 28,
        "order_reference": "PO-123",
        "amount_currency": "USD",
        "amount_value": Decimal("9000.00"),
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "created_at": datetime.now(timezone.utc),
    })

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_active_version_reprocessed_evidence(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Reprocessed evidence includes only its currently active version."""
    case_id = "case_reprocessed"
    await setup_case(fake_db, case_id)
    # evi_1 reprocessed from v1 to v2
    await setup_evidence(fake_db, case_id, "evi_1", "order_v2.pdf", active_version=2)
    await setup_evidence(fake_db, case_id, "evi_2", "receipt.pdf", active_version=1)

    # evi_1 v1 event (superseded)
    await fake_db.events.insert_one({
        "event_id": "evt_v1_1",
        "case_id": case_id,
        "evidence_id": "evi_1",
        "user_id": MOCK_USER,
        "processing_version": 1,
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Order PO-999 v1 $1,000",
        "char_start": 0,
        "char_end": 20,
        "order_reference": "PO-999",
        "amount_currency": "USD",
        "amount_value": Decimal("1000.00"),
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "created_at": datetime.now(timezone.utc),
    })

    # evi_1 v2 event (active)
    await fake_db.events.insert_one({
        "event_id": "evt_v2_1",
        "case_id": case_id,
        "evidence_id": "evi_1",
        "user_id": MOCK_USER,
        "processing_version": 2,
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Order PO-999 v2 $2,000",
        "char_start": 0,
        "char_end": 20,
        "order_reference": "PO-999",
        "amount_currency": "USD",
        "amount_value": Decimal("2000.00"),
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "created_at": datetime.now(timezone.utc),
    })

    # evi_2 v1 event (active)
    await fake_db.events.insert_one({
        "event_id": "evt_v1_2",
        "case_id": case_id,
        "evidence_id": "evi_2",
        "user_id": MOCK_USER,
        "processing_version": 1,
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Order PO-999 receipt $3,000",
        "char_start": 0,
        "char_end": 25,
        "order_reference": "PO-999",
        "amount_currency": "USD",
        "amount_value": Decimal("3000.00"),
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "created_at": datetime.now(timezone.utc),
    })

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    # Compared v2 ($2,000) and v1 ($3,000) -> diff is $1,000, NOT $2,000 from the superseded v1 event
    citation_event_ids = {c["event_id"] for c in items[0]["citations"]}
    assert "evt_v2_1" in citation_event_ids
    assert "evt_v1_2" in citation_event_ids
    assert "evt_v1_1" not in citation_event_ids


@pytest.mark.asyncio
async def test_active_version_no_active_version_or_malformed(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Evidence without active version or with malformed metadata fails safely with 0 findings."""
    case_id = "case_no_ver"
    await setup_case(fake_db, case_id)

    # Document 1: active_processing_version is None
    await fake_db.evidence.insert_one({
        "evidence_id": "evi_none",
        "case_id": case_id,
        "user_id": MOCK_USER,
        "original_filename": "unprocessed.pdf",
        "active_processing_version": None,
        "status": "QUEUED",
        "created_at": datetime.now(timezone.utc),
    })

    # Document 2: active_processing_version is malformed string
    await fake_db.evidence.insert_one({
        "evidence_id": "evi_bad",
        "case_id": case_id,
        "user_id": MOCK_USER,
        "original_filename": "corrupt.pdf",
        "active_processing_version": "v1_bad",
        "status": "READY",
        "created_at": datetime.now(timezone.utc),
    })

    # Document 3: active_processing_version is 0
    await fake_db.evidence.insert_one({
        "evidence_id": "evi_zero",
        "case_id": case_id,
        "user_id": MOCK_USER,
        "original_filename": "zero.pdf",
        "active_processing_version": 0,
        "status": "READY",
        "created_at": datetime.now(timezone.utc),
    })

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_active_version_review_needed_evidence_included(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Evidence with status REVIEW_NEEDED that has an active version is properly evaluated."""
    case_id = "case_rev_needed"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_rev", "doc_rev.pdf", active_version=1, status="REVIEW_NEEDED")
    await setup_evidence(fake_db, case_id, "evi_ready", "doc_ready.pdf", active_version=1, status="READY")

    await fake_db.events.insert_many([
        {
            "event_id": "evt_r_1",
            "case_id": case_id,
            "evidence_id": "evi_rev",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-REV for $5,000",
            "char_start": 0,
            "char_end": 17,
            "order_reference": "PO-REV",
            "amount_currency": "USD",
            "amount_value": Decimal("5000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_r_2",
            "case_id": case_id,
            "evidence_id": "evi_ready",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-REV for $6,000",
            "char_start": 0,
            "char_end": 17,
            "order_reference": "PO-REV",
            "amount_currency": "USD",
            "amount_value": Decimal("6000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1


@pytest.mark.asyncio
async def test_monetary_comparison_conservative_semantics(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Differing amounts on same event type are classified conservatively as POTENTIAL_CONFLICT / MEDIUM, not direct contradiction."""
    case_id = "case_contra"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_contract", "contract.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_confirmation", "confirmation.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_cnt_1",
            "case_id": case_id,
            "evidence_id": "evi_contract",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order PO-700 agreed total $10,000.00",
            "char_start": 10,
            "char_end": 45,
            "page_number": 2,
            "order_reference": "PO-700",
            "amount_currency": "USD",
            "amount_value": Decimal("10000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_cnt_2",
            "case_id": case_id,
            "evidence_id": "evi_confirmation",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order PO-700 stated as $12,500.00",
            "char_start": 5,
            "char_end": 38,
            "page_number": 1,
            "order_reference": "PO-700",
            "amount_currency": "USD",
            "amount_value": Decimal("12500.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    finding = items[0]
    # Refinement 2 check: Must be POTENTIAL_CONFLICT, never DIRECT_CONTRADICTION
    assert finding["conflict_state"] == "POTENTIAL_CONFLICT"
    assert finding["severity"] == "MEDIUM"
    assert "PO-700" in finding["title"]
    assert "line items, tax inclusions, revisions" in finding["summary"].lower()
    assert finding["field_diff"]["field"] == "Amount"
    assert len(finding["citations"]) == 2
    assert finding["citations"][0]["original_filename"] in ["contract.pdf", "confirmation.pdf"]


@pytest.mark.asyncio
async def test_monetary_comparison_uncertain_extraction_insufficient_context(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """When an event has decision_state == REVIEW_NEEDED, finding is classified as INSUFFICIENT_CONTEXT / LOW."""
    case_id = "case_uncertain_amt"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_a", "doc_a.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_b", "doc_b.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_u_1",
            "case_id": case_id,
            "evidence_id": "evi_a",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "REVIEW_NEEDED",  # Uncertain extraction
            "review_reasons": ["LOW_CONFIDENCE"],
            "trigger_raw_text": "PO-UNCERTAIN total $1,000",
            "char_start": 0,
            "char_end": 24,
            "order_reference": "PO-UNCERTAIN",
            "amount_currency": "USD",
            "amount_value": Decimal("1000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "model_confidence": 0.45,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_u_2",
            "case_id": case_id,
            "evidence_id": "evi_b",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-UNCERTAIN total $2,000",
            "char_start": 0,
            "char_end": 24,
            "order_reference": "PO-UNCERTAIN",
            "amount_currency": "USD",
            "amount_value": Decimal("2000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    finding = items[0]
    assert finding["conflict_state"] == "INSUFFICIENT_CONTEXT"
    assert finding["severity"] == "LOW"
    assert "Uncertain Comparison" in finding["title"]
    assert "manual verification is advised" in finding["summary"].lower()


@pytest.mark.asyncio
async def test_currency_mismatch_advisory(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Different currencies on same reference produce POTENTIAL_CONFLICT currency advisory."""
    case_id = "case_curr"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_us", "us_contract.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_eu", "eu_receipt.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_us_1",
            "case_id": case_id,
            "evidence_id": "evi_us",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Total is 50,000 USD on PO-778.",
            "char_start": 0,
            "char_end": 30,
            "order_reference": "PO-778",
            "amount_currency": "USD",
            "amount_value": Decimal("50000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_eu_2",
            "case_id": case_id,
            "evidence_id": "evi_eu",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_CONFIRMED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Paid 45,000 EUR against PO-778.",
            "char_start": 0,
            "char_end": 30,
            "order_reference": "PO-778",
            "amount_currency": "EUR",
            "amount_value": Decimal("45000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    finding = items[0]
    assert finding["conflict_state"] == "POTENTIAL_CONFLICT"
    assert finding["severity"] == "MEDIUM"
    assert "Currency Denomination Mismatch" in finding["title"]
    assert "exchange rate" in finding["summary"].lower()


@pytest.mark.asyncio
async def test_opposing_polarity_conservative(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Opposing polarity on same reference yields conservative POTENTIAL_CONFLICT, never fraud accusations."""
    case_id = "case_pol"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_p1", "affidavit.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_p2", "carrier.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_p_1",
            "case_id": case_id,
            "evidence_id": "evi_p1",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ITEM_DELIVERED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Item was never delivered for PO-POLARITY",
            "char_start": 0,
            "char_end": 40,
            "order_reference": "PO-POLARITY",
            "polarity": "NEGATED",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_p_2",
            "case_id": case_id,
            "evidence_id": "evi_p2",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ITEM_DELIVERED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Item delivered successfully for PO-POLARITY",
            "char_start": 0,
            "char_end": 43,
            "order_reference": "PO-POLARITY",
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    finding = items[0]
    assert finding["conflict_state"] == "POTENTIAL_CONFLICT"
    assert finding["severity"] == "MEDIUM"
    assert "divergent factual claims" in finding["summary"].lower()


@pytest.mark.asyncio
async def test_ambiguous_tokens_and_same_doc_ignored(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Ambiguous tokens ('N/A', 'ID') and same-evidence events never trigger cross-evidence findings."""
    case_id = "case_ambig"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_single", "single.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_other", "other.pdf", active_version=1)

    await fake_db.events.insert_many([
        # Two events in same document with differing amounts
        {
            "event_id": "evt_same_1",
            "case_id": case_id,
            "evidence_id": "evi_single",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Draft PO-999: $100",
            "char_start": 0,
            "char_end": 18,
            "order_reference": "PO-999",
            "amount_currency": "USD",
            "amount_value": Decimal("100.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_same_2",
            "case_id": case_id,
            "evidence_id": "evi_single",  # SAME doc
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Revision PO-999: $200",
            "char_start": 20,
            "char_end": 42,
            "order_reference": "PO-999",
            "amount_currency": "USD",
            "amount_value": Decimal("200.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        # Ambiguous token across docs
        {
            "event_id": "evt_amb_1",
            "case_id": case_id,
            "evidence_id": "evi_single",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_SENT",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Payment sent for ID N/A: $50",
            "char_start": 50,
            "char_end": 75,
            "order_reference": "N/A",
            "amount_currency": "USD",
            "amount_value": Decimal("50.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_amb_2",
            "case_id": case_id,
            "evidence_id": "evi_other",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_SENT",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Payment sent for ID N/A: $70",
            "char_start": 0,
            "char_end": 26,
            "order_reference": "N/A",
            "amount_currency": "USD",
            "amount_value": Decimal("70.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_temporal_sequence_anomaly_conservative(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Explicit timestamps showing shipping before order placement triggers POTENTIAL_CONFLICT temporal finding."""
    case_id = "case_temporal"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_order", "po.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_shipping", "bol.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_order_1",
            "case_id": case_id,
            "evidence_id": "evi_order",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order placed on March 15",
            "char_start": 0,
            "char_end": 24,
            "order_reference": "PO-TEMPORAL",
            "temporal_information": "2026-03-15T09:00:00Z",  # Explicit ISO
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_ship_2",
            "case_id": case_id,
            "evidence_id": "evi_shipping",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_SHIPPED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Dispatched on March 10",
            "char_start": 0,
            "char_end": 22,
            "order_reference": "PO-TEMPORAL",
            "temporal_information": "2026-03-10T14:00:00Z",  # Explicit ISO before order placed!
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    temporal_finding = next((f for f in items if "Temporal Sequence Anomaly" in f["title"]), None)
    assert temporal_finding is not None
    # Conservative semantics check:
    assert temporal_finding["conflict_state"] == "POTENTIAL_CONFLICT"
    assert temporal_finding["severity"] == "MEDIUM"
    assert "differing timezones, retrospective logging" in temporal_finding["summary"].lower()
    assert len(temporal_finding["citations"]) == 2


@pytest.mark.asyncio
async def test_temporal_same_doc_ignored(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Inverted timestamps within the SAME document are ignored (must be cross-document)."""
    case_id = "case_temp_same"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_single_temp", "narrative.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_same_temp_1",
            "case_id": case_id,
            "evidence_id": "evi_single_temp",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Placed March 15",
            "char_start": 0,
            "char_end": 15,
            "order_reference": "PO-SAME-T",
            "temporal_information": "2026-03-15T09:00:00Z",
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_same_temp_2",
            "case_id": case_id,
            "evidence_id": "evi_single_temp",  # SAME evidence document
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_SHIPPED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Shipped March 10",
            "char_start": 20,
            "char_end": 36,
            "order_reference": "PO-SAME-T",
            "temporal_information": "2026-03-10T14:00:00Z",
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_citation_provenance_clean_and_unfabricated(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Citations accurately reflect recorded offsets and pages without fabricating."""
    case_id = "case_citation"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_clean", "contract_clean.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_zero_span", "invoice_zero.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_c_1",
            "case_id": case_id,
            "evidence_id": "evi_clean",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order PO-CITE total $10,000",
            "char_start": 12,
            "char_end": 39,
            "page_number": 3,
            "order_reference": "PO-CITE",
            "amount_currency": "USD",
            "amount_value": Decimal("10000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_c_2",
            "case_id": case_id,
            "evidence_id": "evi_zero_span",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order PO-CITE total $12,000",
            "char_start": 0,
            "char_end": 0,  # default zeros -> should be cleaned to None
            "page_number": None,
            "order_reference": "PO-CITE",
            "amount_currency": "USD",
            "amount_value": Decimal("12000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    cites = items[0]["citations"]
    cite_clean = next(c for c in cites if c["evidence_id"] == "evi_clean")
    cite_zero = next(c for c in cites if c["evidence_id"] == "evi_zero_span")

    # Real offsets preserved
    assert cite_clean["page_number"] == 3
    assert cite_clean["char_start"] == 12
    assert cite_clean["char_end"] == 39
    assert cite_clean["original_filename"] == "contract_clean.pdf"

    # Default zeros cleaned without fabricating
    assert cite_zero["page_number"] is None
    assert cite_zero["char_start"] is None
    assert cite_zero["char_end"] is None
    assert cite_zero["original_filename"] == "invoice_zero.pdf"


@pytest.mark.asyncio
async def test_deterministic_output_and_id_stability(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Successive requests produce identical deterministic finding IDs."""
    case_id = "case_determ"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_a", "file_a.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_b", "file_b.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_d_1",
            "case_id": case_id,
            "evidence_id": "evi_a",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-FIXED $100",
            "char_start": 0,
            "char_end": 13,
            "order_reference": "PO-FIXED",
            "amount_currency": "USD",
            "amount_value": Decimal("100.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_d_2",
            "case_id": case_id,
            "evidence_id": "evi_b",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-FIXED $200",
            "char_start": 0,
            "char_end": 13,
            "order_reference": "PO-FIXED",
            "amount_currency": "USD",
            "amount_value": Decimal("200.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp1 = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})
    resp2 = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-Id": MOCK_USER})

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    items1 = resp1.json()["data"]["items"]
    items2 = resp2.json()["data"]["items"]

    assert len(items1) == 1
    assert len(items2) == 1
    assert items1[0]["finding_id"] == items2[0]["finding_id"]
    assert items1[0]["finding_id"].startswith("fnd_")


@pytest.mark.asyncio
async def test_full_case_evidence_events_findings_flow(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Complete integration test: case creation -> evidence ingestion -> event retrieval -> findings generation."""
    # 1. Create Case
    create_res = await client.post(
        "/api/v1/cases",
        json={"title": "Commercial Dispute Flow", "description": "End-to-end verification case"},
        headers={"X-User-ID": MOCK_USER},
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["data"]["case_id"]

    # 2. Ingest Evidence items
    await setup_evidence(fake_db, case_id, "evi_po_doc", "purchase_order.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_inv_doc", "tax_invoice.pdf", active_version=1)

    # 3. Insert Extracted Events for active version
    await fake_db.events.insert_many([
        {
            "event_id": "evt_e2e_po",
            "case_id": case_id,
            "evidence_id": "evi_po_doc",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Agreed PO-E2E-100 total $5,000.00",
            "char_start": 10,
            "char_end": 42,
            "page_number": 1,
            "order_reference": "PO-E2E-100",
            "amount_currency": "USD",
            "amount_value": Decimal("5000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_e2e_inv",
            "case_id": case_id,
            "evidence_id": "evi_inv_doc",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Billed PO-E2E-100 total $5,500.00",
            "char_start": 15,
            "char_end": 47,
            "page_number": 1,
            "order_reference": "PO-E2E-100",
            "amount_currency": "USD",
            "amount_value": Decimal("5500.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_e2e_unconf",
            "case_id": case_id,
            "evidence_id": "evi_po_doc",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_SENT",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Advance sent under TXN-E2E-999",
            "char_start": 50,
            "char_end": 80,
            "page_number": 2,
            "transaction_reference": "TXN-E2E-999",
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "model_confidence": 0.90,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    # 4. Query Events via API
    events_res = await client.get(
        f"/api/v1/cases/{case_id}/events",
        headers={"X-User-ID": MOCK_USER},
    )
    assert events_res.status_code == 200
    events_data = events_res.json()["data"]
    assert events_data["pagination"]["total"] == 3
    assert len(events_data["items"]) == 3

    # 5. Query Findings via API
    findings_res = await client.get(
        f"/api/v1/cases/{case_id}/findings",
        headers={"X-User-ID": MOCK_USER},
    )
    assert findings_res.status_code == 200
    findings_data = findings_res.json()["data"]
    assert findings_data["case_id"] == case_id
    assert findings_data["total"] == 2

    # Verify amount discrepancy finding
    amt_finding = next(f for f in findings_data["items"] if "PO-E2E-100" in f["title"])
    assert amt_finding["conflict_state"] == "POTENTIAL_CONFLICT"
    assert amt_finding["severity"] == "MEDIUM"
    assert len(amt_finding["citations"]) == 2
    cit_files = {c["original_filename"] for c in amt_finding["citations"]}
    assert cit_files == {"purchase_order.pdf", "tax_invoice.pdf"}

    # Verify missing corroboration finding
    corrob_finding = next(f for f in findings_data["items"] if "TXN-E2E-999" in f["title"])
    assert corrob_finding["finding_type"] == "MISSING_EVIDENCE_ADVISORY"
    assert corrob_finding["conflict_state"] == "POTENTIAL_CONFLICT"
    assert corrob_finding["citations"][0]["original_filename"] == "purchase_order.pdf"

    # 6. Verify Cross-User Isolation
    intruder_events = await client.get(
        f"/api/v1/cases/{case_id}/events",
        headers={"X-User-ID": OTHER_USER},
    )
    assert intruder_events.status_code == 404

    intruder_findings = await client.get(
        f"/api/v1/cases/{case_id}/findings",
        headers={"X-User-ID": OTHER_USER},
    )
    assert intruder_findings.status_code == 404


@pytest.mark.asyncio
async def test_bson_decimal128_full_pipeline_compatibility(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Regression test ensuring BSON Decimal128 compatibility across models, schemas, and findings reasoning."""
    from bson import Decimal128
    from app.models.event import EventDocument
    from app.schemas.event import EventResponse

    # 1. Model & Schema parsing from Decimal128 (zero, fractional, None)
    doc = EventDocument(
        case_id="case_dec",
        evidence_id="evi_dec",
        user_id=MOCK_USER,
        event_type="ORDER_PLACED",
        decision_state="VALIDATED",
        trigger_raw_text="PO-DEC-1 for $1,200.00",
        char_start=0,
        char_end=20,
        amount_value=Decimal128("1200.00"),
    )
    assert doc.amount_value == Decimal("1200.00")

    doc_zero = EventDocument(
        case_id="case_dec",
        evidence_id="evi_dec",
        user_id=MOCK_USER,
        event_type="ORDER_PLACED",
        decision_state="VALIDATED",
        trigger_raw_text="PO-DEC-0 for $0.00",
        char_start=0,
        char_end=19,
        amount_value=Decimal128("0.00"),
    )
    assert doc_zero.amount_value == Decimal("0.00")

    doc_none = EventDocument(
        case_id="case_dec",
        evidence_id="evi_dec",
        user_id=MOCK_USER,
        event_type="ORDER_PLACED",
        decision_state="VALIDATED",
        trigger_raw_text="PO-DEC-None no amount",
        char_start=0,
        char_end=22,
        amount_value=None,
    )
    assert doc_none.amount_value is None

    resp = EventResponse(
        event_id="evt_dec",
        case_id="case_dec",
        evidence_id="evi_dec",
        event_type="ORDER_PLACED",
        decision_state="VALIDATED",
        trigger_raw_text="PO-DEC-1 for $1,200.00",
        char_start=0,
        char_end=20,
        amount_value=Decimal128("12.345"),
        created_at=datetime.now(timezone.utc),
    )
    assert resp.amount_value == Decimal("12.345")

    # 2. Database & API reasoning with Decimal128
    case_id = "case_dec128_flow"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_dec1", "order.pdf")
    await setup_evidence(fake_db, case_id, "evi_dec2", "invoice.pdf")

    await fake_db.events.insert_many([
        {
            "event_id": "evt_dec_1",
            "case_id": case_id,
            "evidence_id": "evi_dec1",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-DEC-99 for $10,000.00",
            "char_start": 0,
            "char_end": 22,
            "order_reference": "PO-DEC-99",
            "amount_currency": "USD",
            "amount_value": Decimal128("10000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_dec_2",
            "case_id": case_id,
            "evidence_id": "evi_dec2",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-DEC-99 billed $11,500.00",
            "char_start": 0,
            "char_end": 25,
            "order_reference": "PO-DEC-99",
            "amount_currency": "USD",
            "amount_value": Decimal128("11500.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    events_res = await client.get(
        f"/api/v1/cases/{case_id}/events",
        headers={"X-User-ID": MOCK_USER},
    )
    assert events_res.status_code == 200
    assert len(events_res.json()["data"]["items"]) == 2

    findings_res = await client.get(
        f"/api/v1/cases/{case_id}/findings",
        headers={"X-User-ID": MOCK_USER},
    )
    assert findings_res.status_code == 200
    findings = findings_res.json()["data"]["items"]
    assert len(findings) == 1
    assert findings[0]["conflict_state"] == "POTENTIAL_CONFLICT"
    assert findings[0]["severity"] == "MEDIUM"
    diff_values = {findings[0]["field_diff"]["value_a"], findings[0]["field_diff"]["value_b"]}
    assert diff_values == {"USD10,000.00", "USD11,500.00"}

    # 3. Currency mismatch with Decimal128
    case_curr_id = "case_dec128_curr"
    await setup_case(fake_db, case_curr_id)
    await setup_evidence(fake_db, case_curr_id, "evi_c1", "doc1.pdf")
    await setup_evidence(fake_db, case_curr_id, "evi_c2", "doc2.pdf")

    await fake_db.events.insert_many([
        {
            "event_id": "evt_c_1",
            "case_id": case_curr_id,
            "evidence_id": "evi_c1",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-CURR for $5,000.00 USD",
            "char_start": 0,
            "char_end": 25,
            "order_reference": "PO-CURR",
            "amount_currency": "USD",
            "amount_value": Decimal128("5000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_c_2",
            "case_id": case_curr_id,
            "evidence_id": "evi_c2",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "PO-CURR for €5,000.00 EUR",
            "char_start": 0,
            "char_end": 25,
            "order_reference": "PO-CURR",
            "amount_currency": "EUR",
            "amount_value": Decimal128("5000.00"),
            "polarity": "POSITIVE",
            "modality": "ASSERTED",
            "tense": "PAST",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    curr_res = await client.get(
        f"/api/v1/cases/{case_curr_id}/findings",
        headers={"X-User-ID": MOCK_USER},
    )
    assert curr_res.status_code == 200
    curr_findings = curr_res.json()["data"]["items"]
    assert len(curr_findings) == 1
    assert "Currency Denomination Mismatch" in curr_findings[0]["title"]
    assert curr_findings[0]["conflict_state"] == "POTENTIAL_CONFLICT"
    assert "EUR" in curr_findings[0]["summary"] and "USD" in curr_findings[0]["summary"]


@pytest.mark.asyncio
async def test_findings_dual_reference_cross_matching(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Event with both order_reference and transaction_reference matches event possessing only transaction_reference."""
    case_id = "case_dual_ref"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_order", "po_order.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_bank", "bank_statement.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_dual_1",
            "case_id": case_id,
            "evidence_id": "evi_order",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order PO-DUAL-100 settled via TXN-DUAL-200 for $3,000.00",
            "char_start": 0,
            "char_end": 50,
            "order_reference": "PO-DUAL-100",
            "transaction_reference": "TXN-DUAL-200",
            "amount_currency": "USD",
            "amount_value": Decimal128("3000.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_dual_2",
            "case_id": case_id,
            "evidence_id": "evi_bank",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_MADE",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Bank wire TXN-DUAL-200 for $3,500.00",
            "char_start": 0,
            "char_end": 35,
            "order_reference": None,
            "transaction_reference": "TXN-DUAL-200",
            "amount_currency": "USD",
            "amount_value": Decimal128("3500.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.98,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(
        f"/api/v1/cases/{case_id}/findings",
        headers={"X-User-ID": MOCK_USER},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert "Amount Divergence" in items[0]["title"]
    assert "TXN-DUAL-200" in items[0]["title"] or "TXNDUAL200" in items[0]["title"]


@pytest.mark.asyncio
async def test_findings_mutually_exclusive_payment_outcomes(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Conflicting settlement outcomes (PAYMENT_MADE vs PAYMENT_FAILED) emit outcome conflict finding."""
    case_id = "case_outcome_conflict"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_succ", "receipt_paid.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_fail", "gateway_decline.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_out_1",
            "case_id": case_id,
            "evidence_id": "evi_succ",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_MADE",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Payment successful for TXN-7777",
            "char_start": 0,
            "char_end": 31,
            "transaction_reference": "TXN-7777",
            "amount_currency": "USD",
            "amount_value": Decimal128("100.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_out_2",
            "case_id": case_id,
            "evidence_id": "evi_fail",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_FAILED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Payment declined for TXN-7777",
            "char_start": 0,
            "char_end": 29,
            "transaction_reference": "TXN-7777",
            "amount_currency": "USD",
            "amount_value": Decimal128("100.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(
        f"/api/v1/cases/{case_id}/findings",
        headers={"X-User-ID": MOCK_USER},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert "Opposing Outcome on Payment Settlement Outcome" in items[0]["title"]
    assert items[0]["conflict_state"] == "POTENTIAL_CONFLICT"
    assert items[0]["severity"] == "MEDIUM"
    assert "retry attempts" in items[0]["summary"].lower()
    assert items[0]["field_diff"]["field"] == "Transaction Status"


@pytest.mark.asyncio
async def test_findings_mutually_exclusive_retry_progression_low_severity(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """When PAYMENT_FAILED precedes PAYMENT_MADE (retry progression), severity is downgraded to LOW."""
    case_id = "case_outcome_retry"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_f", "failed_attempt.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_s", "success_retry.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_ret_1",
            "case_id": case_id,
            "evidence_id": "evi_f",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_FAILED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "First attempt declined for TXN-RETRY",
            "char_start": 0,
            "char_end": 34,
            "transaction_reference": "TXN-RETRY",
            "temporal_information": "2026-06-01T10:00:00Z",  # Failed first at 10:00
            "polarity": "POSITIVE",
            "model_confidence": 0.98,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_ret_2",
            "case_id": case_id,
            "evidence_id": "evi_s",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_MADE",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Retry payment succeeded for TXN-RETRY",
            "char_start": 0,
            "char_end": 37,
            "transaction_reference": "TXN-RETRY",
            "temporal_information": "2026-06-01T10:05:00Z",  # Succeeded 5 mins later at 10:05
            "polarity": "POSITIVE",
            "model_confidence": 0.98,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    # Conservative severity: retry progression is LOW severity, not HIGH
    assert items[0]["severity"] == "LOW"
    assert "probable retry" in items[0]["summary"].lower()



@pytest.mark.asyncio
async def test_adversarial_partial_payment_vs_full_payment(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Partial installment vs full order emits POTENTIAL_CONFLICT noting stage-level differences."""
    case_id = "case_partial_pmt"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_inv", "invoice.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_rec", "receipt.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_p_1",
            "case_id": case_id,
            "evidence_id": "evi_inv",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Invoice total for PO-9900: $10,000.00",
            "char_start": 0,
            "char_end": 35,
            "order_reference": "PO-9900",
            "amount_currency": "USD",
            "amount_value": Decimal128("10000.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.98,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_p_2",
            "case_id": case_id,
            "evidence_id": "evi_rec",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_MADE",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Deposit payment for PO-9900: $3,000.00",
            "char_start": 0,
            "char_end": 37,
            "order_reference": "PO-9900",
            "amount_currency": "USD",
            "amount_value": Decimal128("3000.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.98,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["conflict_state"] == "POTENTIAL_CONFLICT"
    assert "partial payments" in items[0]["summary"].lower()


@pytest.mark.asyncio
async def test_adversarial_refund_requested_corroborated_by_completed(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Refund requested corroborated by refund completed emits no unconfirmed advisory."""
    case_id = "case_refund_corrob"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_req", "refund_request.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_settle", "refund_credit_memo.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_ref_1",
            "case_id": case_id,
            "evidence_id": "evi_req",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "REFUND_REQUESTED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Refund requested for REF-888",
            "char_start": 0,
            "char_end": 28,
            "transaction_reference": "REF-888",
            "amount_currency": "USD",
            "amount_value": Decimal128("200.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_ref_2",
            "case_id": case_id,
            "evidence_id": "evi_settle",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "REFUND_COMPLETED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Refund processed for REF-888",
            "char_start": 0,
            "char_end": 28,
            "transaction_reference": "REF-888",
            "amount_currency": "USD",
            "amount_value": Decimal128("200.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    # Corroborated and amounts equal -> 0 findings
    assert len(items) == 0


@pytest.mark.asyncio
async def test_adversarial_duplicate_uploads_different_evidence_ids(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Identical document re-uploaded under different evidence ID emits 0 findings."""
    case_id = "case_dup_upload"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_orig", "doc_orig.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_copy", "doc_copy.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_d_1",
            "case_id": case_id,
            "evidence_id": "evi_orig",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_MADE",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Paid $500.00 on TXN-DUP-1",
            "char_start": 0,
            "char_end": 25,
            "transaction_reference": "TXN-DUP-1",
            "amount_currency": "USD",
            "amount_value": Decimal128("500.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.99,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_d_2",
            "case_id": case_id,
            "evidence_id": "evi_copy",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_MADE",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Paid $500.00 on TXN-DUP-1",
            "char_start": 0,
            "char_end": 25,
            "transaction_reference": "TXN-DUP-1",
            "amount_currency": "USD",
            "amount_value": Decimal128("500.00"),
            "polarity": "POSITIVE",
            "model_confidence": 0.99,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 0


@pytest.mark.asyncio
async def test_adversarial_timezone_offsets_and_date_only_values(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Mixed date-only strings and offset-aware datetimes compare safely in UTC without TypeError."""
    case_id = "case_tz_safe"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_order", "order.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_ship", "tracking.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_tz_1",
            "case_id": case_id,
            "evidence_id": "evi_order",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order PO-TZ placed",
            "char_start": 0,
            "char_end": 18,
            "order_reference": "PO-TZ",
            "temporal_information": "2026-05-10",  # date-only naive
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_tz_2",
            "case_id": case_id,
            "evidence_id": "evi_ship",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ITEM_SHIPPED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Shipped ahead of order",
            "char_start": 0,
            "char_end": 22,
            "order_reference": "PO-TZ",
            "temporal_information": "2026-05-09T18:00:00+02:00",  # offset-aware (May 9 16:00 UTC)
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert "Temporal Sequence Anomaly" in items[0]["title"]


@pytest.mark.asyncio
async def test_adversarial_intra_document_conflicts_isolated(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Contradicting events within the same evidence document are not treated as cross-evidence inconsistencies."""
    case_id = "case_intra_doc"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_single", "single_multi_page.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_intra_1",
            "case_id": case_id,
            "evidence_id": "evi_single",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_MADE",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Page 1: Payment success for TXN-INTRA",
            "char_start": 0,
            "char_end": 35,
            "page_number": 1,
            "transaction_reference": "TXN-INTRA",
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_intra_2",
            "case_id": case_id,
            "evidence_id": "evi_single",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "PAYMENT_FAILED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Page 2: Payment failed for TXN-INTRA",
            "char_start": 0,
            "char_end": 34,
            "page_number": 2,
            "transaction_reference": "TXN-INTRA",
            "polarity": "POSITIVE",
            "model_confidence": 0.95,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 0


@pytest.mark.asyncio
async def test_adversarial_malformed_amounts_and_dates_fail_safely(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Non-numeric amounts and unparseable date strings fail safely without exceptions or spurious findings."""
    case_id = "case_malformed_safe"
    await setup_case(fake_db, case_id)
    await setup_evidence(fake_db, case_id, "evi_bad_a", "bad_a.pdf", active_version=1)
    await setup_evidence(fake_db, case_id, "evi_bad_b", "bad_b.pdf", active_version=1)

    await fake_db.events.insert_many([
        {
            "event_id": "evt_m_1",
            "case_id": case_id,
            "evidence_id": "evi_bad_a",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ORDER_PLACED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Order PO-MALFORMED",
            "char_start": 0,
            "char_end": 18,
            "order_reference": "PO-MALFORMED",
            "amount_currency": "USD",
            "amount_value": "not-a-number",
            "temporal_information": "invalid-datetime-string",
            "polarity": "POSITIVE",
            "model_confidence": 0.90,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "event_id": "evt_m_2",
            "case_id": case_id,
            "evidence_id": "evi_bad_b",
            "user_id": MOCK_USER,
            "processing_version": 1,
            "is_active": True,
            "event_type": "ITEM_SHIPPED",
            "decision_state": "VALIDATED",
            "review_reasons": [],
            "trigger_raw_text": "Shipped PO-MALFORMED",
            "char_start": 0,
            "char_end": 20,
            "order_reference": "PO-MALFORMED",
            "amount_currency": None,
            "amount_value": None,
            "temporal_information": None,
            "polarity": "POSITIVE",
            "model_confidence": 0.90,
            "created_at": datetime.now(timezone.utc),
        },
    ])

    resp = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": MOCK_USER})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 0
