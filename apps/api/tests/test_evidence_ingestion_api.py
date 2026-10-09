from decimal import Decimal
import io
import os
import pymupdf
import pytest
from httpx import AsyncClient

from app.models.evidence import EvidenceStatus, MLProcessingMode
from app.services.evidence_processor import (
    ProcessingJob,
    evidence_processing_service,
)
from app.services.storage import storage_service


def make_sample_pdf_bytes(text: str = "Customer placed an order ORD-12345 for $99.00 on 2026-08-10.") -> bytes:
    """Generates valid in-memory PDF binary bytes."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_sample_png_bytes() -> bytes:
    """Generates minimal valid 1x1 PNG bytes."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.mark.asyncio
async def test_upload_valid_pdf_and_background_processing(client: AsyncClient, fake_db):
    """Verifies complete streaming upload, atomic storage, and end-to-end background extraction."""
    # 1. Create case
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Case for PDF upload"},
        headers={"X-User-ID": "usr_alice"},
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["data"]["case_id"]

    # 2. Upload valid PDF
    pdf_bytes = make_sample_pdf_bytes("Customer placed an order ORD-99120 for $450.00 on 2026-09-15.")
    files = {"file": ("order.pdf", pdf_bytes, "application/pdf")}

    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert upload_res.status_code == 201
    body = upload_res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["evidence_id"].startswith("evi_")
    assert data["case_id"] == case_id
    assert data["status"] == "QUEUED"
    assert data["is_duplicate"] is False
    assert data["media_type"] == "application/pdf"
    assert len(data["sha256_hash"]) == 64

    evidence_id = data["evidence_id"]

    # 3. Verify file exists in private storage
    doc_in_db = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert doc_in_db is not None
    rel_path = doc_in_db["storage_relative_path"]
    stored_bytes = storage_service.read_evidence_bytes(rel_path)
    assert len(stored_bytes) == len(pdf_bytes)

    # 4. Execute background processing job directly with fake_db
    job = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=rel_path,
        original_filename="order.pdf",
        media_type="application/pdf",
        sha256_hash=data["sha256_hash"],
    )
    await evidence_processing_service.run_job(job, fake_db)

    # 5. Check updated status and extraction summary
    detail_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}",
        headers={"X-User-ID": "usr_alice"},
    )
    assert detail_res.status_code == 200
    detail_data = detail_res.json()["data"]
    assert detail_data["status"] in ("READY", "REVIEW_NEEDED")
    assert detail_data["processing_mode"] == MLProcessingMode.DETERMINISTIC_FALLBACK.value
    assert detail_data["extraction_summary"]["page_count"] == 1
    assert detail_data["extraction_summary"]["events_extracted"] >= 1

    # Cleanup stored test file
    storage_service.remove_evidence_file(rel_path)


@pytest.mark.asyncio
async def test_upload_valid_png(client: AsyncClient, fake_db):
    """Verifies image evidence upload passes magic byte validation."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Image Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    png_bytes = make_sample_png_bytes()
    files = {"file": ("receipt.png", png_bytes, "image/png")}

    res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["media_type"] == "image/png"

    # Cleanup
    doc = await fake_db.evidence.find_one({"evidence_id": res.json()["data"]["evidence_id"]})
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_reject_empty_file(client: AsyncClient):
    """Verifies 0-byte file is rejected immediately with 400."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Empty File Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    files = {"file": ("empty.pdf", b"", "application/pdf")}
    res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_reject_mime_signature_mismatch(client: AsyncClient):
    """Verifies declared PDF with plain text bytes is rejected."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Mismatch Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    files = {"file": ("fake.pdf", b"This is just plain text, not a PDF header", "application/pdf")}
    res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res.status_code == 400
    assert "magic bytes" in res.json()["error"]["message"].lower() or "signature" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_reject_unsupported_file_extension(client: AsyncClient):
    """Verifies unsupported executable/script extensions are rejected with 415."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Extension Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    files = {"file": ("malicious.exe", b"%PDF-1.4 header spoofing", "application/pdf")}
    res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res.status_code == 415
    assert "Unsupported file extension" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_reject_corrupted_pdf(client: AsyncClient):
    """Verifies malformed PDF header without valid document structure is rejected with 400."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Corrupted Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    corrupted_bytes = b"%PDF-1.4 truncated garbage content with no xref or trailer"
    files = {"file": ("corrupt.pdf", corrupted_bytes, "application/pdf")}
    res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res.status_code == 400
    assert "corrupted" in res.json()["error"]["message"].lower() or "pdf" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_reject_oversized_file(client: AsyncClient, monkeypatch):
    """Verifies streaming limit aborts and cleans up temp file when file exceeds max size."""
    from app.core import config
    monkeypatch.setattr(config.settings, "MAX_EVIDENCE_FILE_SIZE_BYTES", 500)

    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Oversized Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Large text content that exceeds 500 bytes easily when rendered as PDF structure.")
    files = {"file": ("large.pdf", pdf_bytes, "application/pdf")}

    res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res.status_code == 413
    assert "exceeds maximum permitted size" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_case_ownership_security(client: AsyncClient):
    """Verifies user B cannot upload evidence to user A's case."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Alice Private Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes()
    files = {"file": ("order.pdf", pdf_bytes, "application/pdf")}

    # User Bob attempts upload to Alice's case
    res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_bob"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_upload_policy(client: AsyncClient, fake_db):
    """Verifies duplicate uploads within the same case return the existing record without duplicate storage."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Dedup Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Unique text for deduplication verification.")
    files1 = {"file": ("order.pdf", pdf_bytes, "application/pdf")}

    # First upload
    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files1,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res1.status_code == 201
    data1 = res1.json()["data"]
    assert data1["is_duplicate"] is False

    # Second upload with identical bytes
    files2 = {"file": ("order_copy.pdf", pdf_bytes, "application/pdf")}
    res2 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files2,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res2.status_code == 201
    data2 = res2.json()["data"]
    assert data2["is_duplicate"] is True
    assert data2["evidence_id"] == data1["evidence_id"]
    assert data2["sha256_hash"] == data1["sha256_hash"]

    # Verify only 1 record exists in database
    count = await fake_db.evidence.count_documents({"case_id": case_id})
    assert count == 1

    # Cleanup
    doc = await fake_db.evidence.find_one({"evidence_id": data1["evidence_id"]})
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_events_retrieval_endpoints(client: AsyncClient, fake_db):
    """Verifies GET /cases/{case_id}/events and GET /cases/{case_id}/evidence/{evidence_id}/events."""
    # 1. Setup case and evidence
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Events Test Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Customer placed an order ORD-77889 for $120.00 on 2026-09-01.")
    files = {"file": ("order.pdf", pdf_bytes, "application/pdf")}
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Process job to populate events
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    job = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
    )
    await evidence_processing_service.run_job(job, fake_db)

    # 2. Test GET /cases/{case_id}/events
    events_res = await client.get(
        f"/api/v1/cases/{case_id}/events",
        headers={"X-User-ID": "usr_alice"},
    )
    assert events_res.status_code == 200
    events_body = events_res.json()
    assert events_body["success"] is True
    items = events_body["data"]["items"]
    assert len(items) >= 1
    assert items[0]["case_id"] == case_id
    assert items[0]["evidence_id"] == evidence_id
    assert items[0]["decision_state"] in ("VALIDATED", "REVIEW_NEEDED")

    # 3. Test GET /cases/{case_id}/evidence/{evidence_id}/events
    evi_events_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/events",
        headers={"X-User-ID": "usr_alice"},
    )
    assert evi_events_res.status_code == 200
    evi_items = evi_events_res.json()["data"]["items"]
    assert len(evi_items) == len(items)

    # Cleanup
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_retry_processing_and_versioning(client: AsyncClient, fake_db):
    """Verifies that retrying a failed evidence asset increments retry_count and versioning replaces events safely."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Retry Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Customer placed an order ORD-44556 for $200.00.")
    files = {"file": ("invoice.pdf", pdf_bytes, "application/pdf")}
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Manually set status to FAILED to simulate failure
    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"status": EvidenceStatus.FAILED.value, "error_code": "SIMULATED_FAILURE"}},
    )

    # Trigger retry endpoint
    retry_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/retry",
        headers={"X-User-ID": "usr_alice"},
    )
    assert retry_res.status_code == 202
    retry_data = retry_res.json()["data"]
    assert retry_data["status"] == "QUEUED"

    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert doc["retry_count"] == 1

    # Now execute job
    job = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="invoice.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=1,
    )
    await evidence_processing_service.run_job(job, fake_db)

    # Verify status completed
    updated_doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert updated_doc["status"] in ("READY", "REVIEW_NEEDED")
    assert updated_doc["processing_version"] == 2

    # Cleanup
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_upload_nonexistent_case(client: AsyncClient):
    """Verifies uploading to a non-existent case returns 404."""
    pdf_bytes = make_sample_pdf_bytes()
    files = {"file": ("order.pdf", pdf_bytes, "application/pdf")}
    res = await client.post(
        "/api/v1/cases/case_nonexistent_99999/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_retry_invalid_status_rejected(client: AsyncClient, fake_db):
    """Verifies that attempting to retry an evidence that is already QUEUED or READY returns 400."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Retry Status Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes()
    files = {"file": ("sample.pdf", pdf_bytes, "application/pdf")}
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Status is QUEUED; retry should be rejected with 400
    retry_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/retry",
        headers={"X-User-ID": "usr_alice"},
    )
    assert retry_res.status_code == 400
    assert "Cannot retry evidence with status" in retry_res.json()["error"]["message"]

    # Cleanup
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_list_case_evidence_pagination(client: AsyncClient, fake_db):
    """Verifies GET /cases/{case_id}/evidence lists paginated items with pagination metadata."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "List Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    # Upload two distinct evidence items
    pdf1 = make_sample_pdf_bytes("First distinct evidence content.")
    pdf2 = make_sample_pdf_bytes("Second distinct evidence content.")

    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("doc1.pdf", pdf1, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    res2 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("doc2.pdf", pdf2, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    assert res1.status_code == 201
    assert res2.status_code == 201

    list_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence?page=1&limit=10",
        headers={"X-User-ID": "usr_alice"},
    )
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["success"] is True
    assert len(body["data"]["items"]) == 2
    assert body["data"]["pagination"]["total"] == 2

    # Cleanup
    for item in body["data"]["items"]:
        doc = await fake_db.evidence.find_one({"evidence_id": item["evidence_id"]})
        storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_honest_ml_processing_mode_metadata(client: AsyncClient, fake_db):
    """Verifies that in test environment without GPU, MLProcessingMode accurately reflects fallback."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "ML Mode Honesty Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Customer paid $50.00 for order ORD-11.")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("order.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})

    job = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
    )
    await evidence_processing_service.run_job(job, fake_db)

    detail_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}",
        headers={"X-User-ID": "usr_alice"},
    )
    detail_data = detail_res.json()["data"]
    # In test/API environment, mode must NEVER claim NEURAL_DEBERTA_GPU
    assert detail_data["processing_mode"] == MLProcessingMode.DETERMINISTIC_FALLBACK.value

    # Cleanup
    storage_service.remove_evidence_file(doc["storage_relative_path"])

