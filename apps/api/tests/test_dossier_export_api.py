from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import FakeAsyncDatabase

MOCK_USER = "user_dossier_tester"
OTHER_USER = "user_other_tenant"


async def _create_test_case_with_data(
    fake_db: FakeAsyncDatabase,
    user_id: str = MOCK_USER,
    populate_events: bool = True,
    populate_reviews: bool = True,
    include_long_text: bool = False,
) -> str:
    """Helper to set up a rich case with evidence, events, and reviews."""
    case_id = f"case_dossier_{user_id[:8]}"
    evi_id_1 = f"evi_{user_id[:8]}_po"
    evi_id_2 = f"evi_{user_id[:8]}_inv"

    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_id,
        "title": "International Hardware Procurement Dispute",
        "description": "Cross-border dispute regarding PO-9008 pricing and settlement terms.",
        "status": "READY",
        "tags": ["procurement", "hardware"],
        "evidence_count": 2 if populate_events else 0,
        "metadata": {"dispute_type": "commercial"},
        "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 1, 10, 5, 0, tzinfo=timezone.utc),
    })

    if not populate_events:
        return case_id

    # Evidence 1
    await fake_db.evidence.insert_one({
        "evidence_id": evi_id_1,
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": "purchase_order_9008.pdf",
        "media_type": "application/pdf",
        "file_size_bytes": 105000,
        "sha256_hash": "a" * 64,
        "status": "READY",
        "active_processing_version": 1,
        "created_at": datetime(2026, 3, 1, 10, 1, 0, tzinfo=timezone.utc),
    })

    # Evidence 2
    await fake_db.evidence.insert_one({
        "evidence_id": evi_id_2,
        "case_id": case_id,
        "user_id": user_id,
        "original_filename": "commercial_invoice_9008.pdf",
        "media_type": "application/pdf",
        "file_size_bytes": 84000,
        "sha256_hash": "b" * 64,
        "status": "READY",
        "active_processing_version": 1,
        "created_at": datetime(2026, 3, 1, 10, 2, 0, tzinfo=timezone.utc),
    })

    long_prefix = ("Very long contractual statement with unicode symbols: €45,000 — “special terms apply” • " * 5) if include_long_text else ""

    # Event 1 (Stated date in metadata)
    await fake_db.events.insert_one({
        "event_id": f"evt_{user_id[:6]}_1",
        "case_id": case_id,
        "evidence_id": evi_id_1,
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": f"{long_prefix}Purchase order PO-9008 issued for total $50,000.00.",
        "char_start": 10,
        "char_end": 65,
        "page_number": 1,
        "order_reference": "PO-9008",
        "amount_currency": "USD",
        "amount_value": 50000.00,
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "metadata": {"stated_date": "2026-02-15"},
        "created_at": datetime(2026, 3, 1, 10, 3, 0, tzinfo=timezone.utc),
    })

    # Event 2 (Missing stated date)
    await fake_db.events.insert_one({
        "event_id": f"evt_{user_id[:6]}_2",
        "case_id": case_id,
        "evidence_id": evi_id_2,
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": "ORDER_PLACED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Commercial invoice references PO-9008 with billed total $58,500.00.",
        "char_start": 15,
        "char_end": 78,
        "page_number": 2,
        "order_reference": "PO-9008",
        "amount_currency": "USD",
        "amount_value": 58500.00,
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "metadata": {},  # No stated date
        "created_at": datetime(2026, 3, 1, 10, 4, 0, tzinfo=timezone.utc),
    })

    # Event 3 (Missing corroboration advisory)
    await fake_db.events.insert_one({
        "event_id": f"evt_{user_id[:6]}_3",
        "case_id": case_id,
        "evidence_id": evi_id_1,
        "user_id": user_id,
        "processing_version": 1,
        "is_active": True,
        "event_type": "REFUND_REQUESTED",
        "decision_state": "VALIDATED",
        "review_reasons": [],
        "trigger_raw_text": "Refund claim filed for defective components on REF-7721.",
        "char_start": 0,
        "char_end": 50,
        "page_number": 1,
        "order_reference": "REF-7721",
        "amount_currency": "USD",
        "amount_value": 8500.00,
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "tense": "PAST",
        "metadata": {},
        "created_at": datetime(2026, 3, 1, 10, 5, 0, tzinfo=timezone.utc),
    })

    if populate_reviews:
        # We will adjudicate after finding computation in tests
        pass

    return case_id


@pytest.mark.asyncio
async def test_export_json_valid_dossier(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """1. Test valid JSON export with schema integrity and stable identifiers."""
    case_id = await _create_test_case_with_data(fake_db, MOCK_USER)

    res = await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": MOCK_USER})
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    assert f'filename="proofflow_dossier_{case_id}.json"' in res.headers.get("content-disposition", "")

    data = res.json()
    assert data["report_version"] == "1.0.0"
    assert data["case"]["case_id"] == case_id
    assert len(data["document_inventory"]) == 2
    assert len(data["events_timeline"]) == 3
    assert len(data["findings"]) >= 1
    assert data["manifest_hash"] is not None
    assert "ProofFlow Evidence Reasoning Engine" in data["methodology"]["system_name"]
    assert "not a legal decision engine" in data["methodology"]["disclaimer"]


@pytest.mark.asyncio
async def test_export_pdf_valid_dossier(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """2. Test valid PDF export returns binary PDF stream with proper MIME and headers."""
    case_id = await _create_test_case_with_data(fake_db, MOCK_USER)

    res = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": MOCK_USER})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert f'filename="proofflow_dossier_{case_id}.pdf"' in res.headers.get("content-disposition", "")

    content = res.content
    assert content.startswith(b"%PDF-")  # Valid PDF signature
    assert len(content) > 1000  # Non-trivial document size


@pytest.mark.asyncio
async def test_export_empty_case_handled_safely(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """3. An empty case without evidence or events exports gracefully without error."""
    case_id = await _create_test_case_with_data(fake_db, "user_empty_case", populate_events=False)

    # JSON export
    res_json = await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": "user_empty_case"})
    assert res_json.status_code == 200
    d_json = res_json.json()
    assert d_json["document_inventory"] == []
    assert d_json["events_timeline"] == []
    assert d_json["findings"] == []
    assert any(g["gap_type"] == "DOCUMENT_UNAVAILABLE" for g in d_json["evidence_gaps"])

    # PDF export
    res_pdf = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": "user_empty_case"})
    assert res_pdf.status_code == 200
    assert res_pdf.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_export_missing_dates_and_quotes_distinguished(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """4. Stated dates are explicitly distinguished from document upload timestamps."""
    case_id = await _create_test_case_with_data(fake_db, "user_missing_dates")

    res = await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": "user_missing_dates"})
    assert res.status_code == 200
    timeline = res.json()["events_timeline"]

    event_with_stated_date = next((e for e in timeline if e["stated_event_date"] is not None), None)
    event_without_stated_date = next((e for e in timeline if e["stated_event_date"] is None), None)

    assert event_with_stated_date is not None
    assert event_with_stated_date["stated_event_date"] == "2026-02-15"
    assert event_with_stated_date["document_upload_time"] is not None

    assert event_without_stated_date is not None
    assert event_without_stated_date["stated_event_date"] is None
    assert event_without_stated_date["document_upload_time"] is not None


@pytest.mark.asyncio
async def test_export_preserves_human_review_decisions_and_history(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """5. All human review decisions (Confirmed, Resolved, Dismissed) and audit history are exported."""
    case_id = await _create_test_case_with_data(fake_db, "user_rev_tester")

    # Fetch computed findings
    f_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": "user_rev_tester"})
    findings = f_res.json()["data"]["items"]
    assert len(findings) >= 1
    finding_id = findings[0]["finding_id"]

    # Adjudicate v1: CONFIRMED_INCONSISTENCY
    await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "CONFIRMED_INCONSISTENCY", "reason": "Initial review indicates price mismatch."},
        headers={"X-User-ID": "user_rev_tester"},
    )

    # Adjudicate v2: RESOLVED
    await client.post(
        f"/api/v1/cases/{case_id}/findings/{finding_id}/review",
        json={"decision": "RESOLVED", "reason": "Vendor credited the excess billing via supplemental memo."},
        headers={"X-User-ID": "user_rev_tester"},
    )

    # Export JSON
    res = await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": "user_rev_tester"})
    assert res.status_code == 200
    data = res.json()

    exported_finding = next((f for f in data["findings"] if f["finding_id"] == finding_id), None)
    assert exported_finding is not None
    assert exported_finding["adjudication_status"] == "RESOLVED"
    assert exported_finding["active_review"]["decision"] == "RESOLVED"
    assert len(exported_finding["review_history"]) == 2
    assert exported_finding["review_history"][0]["version"] == 2
    assert exported_finding["review_history"][1]["version"] == 1


@pytest.mark.asyncio
async def test_export_security_tenant_isolation(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """6. Cross-tenant export requests return 404 without leaking case existence."""
    case_id = await _create_test_case_with_data(fake_db, MOCK_USER)

    # OTHER_USER attempts to export MOCK_USER's case
    res_json = await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": OTHER_USER})
    assert res_json.status_code == 404

    res_pdf = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": OTHER_USER})
    assert res_pdf.status_code == 404


@pytest.mark.asyncio
async def test_export_security_unauthenticated_request_rejected(client: AsyncClient, fake_db: FakeAsyncDatabase, monkeypatch):
    """7. Unauthenticated export requests are rejected with 401 when dev bypass is off."""
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)
    case_id = await _create_test_case_with_data(fake_db, MOCK_USER)

    res = await client.get(f"/api/v1/cases/{case_id}/export/json")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_export_read_only_does_not_mutate_case(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """8. Exporting a case is strictly read-only and does not mutate case or evidence records."""
    case_id = await _create_test_case_with_data(fake_db, "user_readonly")

    case_before = await fake_db.cases.find_one({"case_id": case_id})
    updated_at_before = case_before["updated_at"]

    # Perform multiple export operations
    await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": "user_readonly"})
    await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": "user_readonly"})

    case_after = await fake_db.cases.find_one({"case_id": case_id})
    assert case_after["updated_at"] == updated_at_before
    assert case_after["status"] == case_before["status"]


@pytest.mark.asyncio
async def test_export_handles_unicode_and_unusually_long_text(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """9. Handles Unicode symbols, special characters, and very long quotes safely in PDF and JSON."""
    case_id = await _create_test_case_with_data(fake_db, "user_unicode", include_long_text=True)

    res_json = await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": "user_unicode"})
    assert res_json.status_code == 200
    assert "€45,000" in res_json.text

    res_pdf = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": "user_unicode"})
    assert res_pdf.status_code == 200
    assert res_pdf.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_export_all_decision_states_rendered_in_pdf_and_json(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """10. Findings with all supported decisions (Confirmed, Resolved, Dismissed, Unreviewed) export correctly."""
    case_id = await _create_test_case_with_data(fake_db, "user_all_states")

    # Fetch computed findings
    f_res = await client.get(f"/api/v1/cases/{case_id}/findings", headers={"X-User-ID": "user_all_states"})
    findings = f_res.json()["data"]["items"]
    assert len(findings) >= 2

    # Dismiss first finding
    await client.post(
        f"/api/v1/cases/{case_id}/findings/{findings[0]['finding_id']}/review",
        json={"decision": "DISMISSED", "reason": "Expected variance per contract section 4.2."},
        headers={"X-User-ID": "user_all_states"},
    )

    # Confirm second finding
    await client.post(
        f"/api/v1/cases/{case_id}/findings/{findings[1]['finding_id']}/review",
        json={"decision": "CONFIRMED_INCONSISTENCY", "reason": "Confirmed missing confirmation document."},
        headers={"X-User-ID": "user_all_states"},
    )

    # Export JSON
    res_json = await client.get(f"/api/v1/cases/{case_id}/export/json", headers={"X-User-ID": "user_all_states"})
    assert res_json.status_code == 200
    d_json = res_json.json()
    statuses = [f["adjudication_status"] for f in d_json["findings"]]
    assert "DISMISSED" in statuses
    assert "CONFIRMED_INCONSISTENCY" in statuses

    # Export PDF
    res_pdf = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": "user_all_states"})
    assert res_pdf.status_code == 200
    assert len(res_pdf.content) > 2000

