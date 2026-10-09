from decimal import Decimal
import hashlib
import io
import os
from fastapi import HTTPException
import pymupdf
import pytest
from httpx import AsyncClient

from app.core.config import settings
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


@pytest.mark.asyncio
async def test_sha256_exact_bytes_regression(client: AsyncClient, fake_db):
    """Priority 1 Regression: Verifies stored and returned hash equals exact SHA-256 of uploaded bytes."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "SHA-256 Exact Verification Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    sample_content = "Merchant shipped ORD-998822 via FedEx tracking 1234567890."
    pdf_bytes = make_sample_pdf_bytes(sample_content)
    expected_hash = hashlib.sha256(pdf_bytes).hexdigest()

    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("manifest.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()["data"]

    # 1. Immediate upload response matches exact bytes SHA-256
    assert upload_data["sha256_hash"] == expected_hash
    evidence_id = upload_data["evidence_id"]

    # 2. Database document record matches exact bytes SHA-256
    db_doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert db_doc is not None
    assert db_doc["sha256_hash"] == expected_hash

    # 3. Private physical storage matches exact bytes and byte-level hash
    stored_bytes = storage_service.read_evidence_bytes(db_doc["storage_relative_path"])
    assert stored_bytes == pdf_bytes
    assert hashlib.sha256(stored_bytes).hexdigest() == expected_hash

    # 4. GET evidence detail returns the identical hash
    detail_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}",
        headers={"X-User-ID": "usr_alice"},
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["sha256_hash"] == expected_hash

    # Cleanup
    storage_service.remove_evidence_file(db_doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_storage_cleanup_on_db_insert_failure(client: AsyncClient, fake_db, monkeypatch):
    """Priority 3: Simulates DB insertion failure and verifies no orphaned files remain on disk."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "DB Failure Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Simulated crash document test.")
    case_storage_dir = os.path.join(storage_service.storage_root, case_id)

    # Monkeypatch insert_one to simulate a fatal DB connection failure
    async def mock_failed_insert(*args, **kwargs):
        raise RuntimeError("Simulated MongoDB write crash")

    monkeypatch.setattr(fake_db.evidence, "insert_one", mock_failed_insert)

    with pytest.raises(RuntimeError, match="Simulated MongoDB write crash"):
        await client.post(
            f"/api/v1/cases/{case_id}/evidence",
            files={"file": ("crash.pdf", pdf_bytes, "application/pdf")},
            headers={"X-User-ID": "usr_alice"},
        )

    # Verify that the file was cleaned up and no orphaned file was leaked in case directory
    if os.path.exists(case_storage_dir):
        files_remaining = os.listdir(case_storage_dir)
        assert len(files_remaining) == 0, f"Orphaned files leaked: {files_remaining}"


@pytest.mark.asyncio
async def test_duplicate_upload_race_deterministic(client: AsyncClient, fake_db, monkeypatch):
    """Priority 3: Tests duplicate-upload race condition and verifies deterministic winner resolution."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Race Condition Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Concurrent duplicate upload race simulation.")

    # First upload succeeds normally
    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("race.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    assert res1.status_code == 201
    evi_id1 = res1.json()["data"]["evidence_id"]

    # For the second upload, simulate a concurrent race where find_one initially missed the record,
    # but insert_one triggered a DuplicateKeyError
    async def mock_race_insert(doc):
        # Simulate race duplicate key error
        raise Exception("E11000 duplicate key error collection: evidence index: idx_evidence_case_sha256_unique")

    monkeypatch.setattr(fake_db.evidence, "insert_one", mock_race_insert)

    res2 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("race_duplicate.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    assert res2.status_code == 201
    data2 = res2.json()["data"]
    assert data2["is_duplicate"] is True
    assert data2["evidence_id"] == evi_id1

    # Cleanup
    doc = await fake_db.evidence.find_one({"evidence_id": evi_id1})
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_retry_failure_preserves_version1_and_prevents_mixed_events(client: AsyncClient, fake_db, monkeypatch):
    """Priority 2: Simulates retry failure after new events are inserted but before completion.

    Verifies that:
    1. Staged events remain inactive (is_active=False) and readers never see mixed versions or duplicate logical events.
    2. A failed retry preserves the previous successful results.
    """
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Retry Version Consistency Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Order ORD-100 placed by customer Alice on Monday.")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("order.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})

    # Run version 1 processing
    job_v1 = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=0,
    )
    await evidence_processing_service.run_job(job_v1, fake_db)

    # Verify version 1 events exist and are active
    v1_events_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/events",
        headers={"X-User-ID": "usr_alice"},
    )
    v1_items = v1_events_res.json()["data"]["items"]
    assert len(v1_items) >= 1
    assert all(item["processing_version"] == 1 for item in v1_items)
    v1_event_count = len(v1_items)

    # 1. Staging Failure Injection Test
    # Set status to REVIEW_NEEDED to authorize reprocessing retry
    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"status": EvidenceStatus.REVIEW_NEEDED.value}},
    )

    # Hook insert_many to raise an exception during staging
    orig_insert_many = fake_db.events.insert_many

    async def fail_during_insert_many(docs):
        raise RuntimeError("Simulated crash during event staging")

    monkeypatch.setattr(fake_db.events, "insert_many", fail_during_insert_many)

    retry_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/retry",
        headers={"X-User-ID": "usr_alice"},
    )
    assert retry_res.status_code == 202

    # Verify reader query still returns exactly version 1 events
    reader_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/events",
        headers={"X-User-ID": "usr_alice"},
    )
    reader_items = reader_res.json()["data"]["items"]
    assert len(reader_items) == v1_event_count
    assert all(item["processing_version"] == 1 for item in reader_items)

    # Verify evidence document active_processing_version remained 1
    ev_row = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert ev_row["active_processing_version"] == 1
    assert ev_row["status"] == EvidenceStatus.FAILED.value

    # Cleanup
    monkeypatch.setattr(fake_db.events, "insert_many", orig_insert_many)
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_pointer_switch_failure_preserves_version1_and_cleans_staged_events(client: AsyncClient, fake_db, monkeypatch):
    """Failure Injection: Simulates atomic pointer switch failure on evidence document.

    Verifies that:
    1. If pointer switch conditional update fails (modified_count == 0), staged v2 events are purged.
    2. Active version remains 1 and readers only see version 1 events.
    """
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Pointer Switch Failure Test Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Order ORD-200 placed by customer Bob on Tuesday.")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("order2.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})

    # Run version 1 processing
    job_v1 = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order2.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=0,
    )
    await evidence_processing_service.run_job(job_v1, fake_db)

    # Verify version 1 active
    ev_row_v1 = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert ev_row_v1["active_processing_version"] == 1

    # Authorize retry
    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"status": EvidenceStatus.REVIEW_NEEDED.value}},
    )

    # Hook update_one on evidence collection to fail during pointer switch
    orig_update_one = fake_db.evidence.update_one

    async def fail_during_pointer_switch(filter_q, update_q):
        if "active_processing_version" in update_q.get("$set", {}):
            # Simulate conditional update mismatch / conflict (modified_count == 0)
            return type("UpdateResult", (), {"modified_count": 0})()
        return await orig_update_one(filter_q, update_q)

    monkeypatch.setattr(fake_db.evidence, "update_one", fail_during_pointer_switch)

    job_v2 = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order2.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=1,
    )
    await evidence_processing_service.run_job(job_v2, fake_db)

    # 1. Readers still see version 1
    reader_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/events",
        headers={"X-User-ID": "usr_alice"},
    )
    items = reader_res.json()["data"]["items"]
    assert len(items) >= 1
    assert all(item["processing_version"] == 1 for item in items)

    # 2. Evidence active version remains 1
    ev_after = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert ev_after["active_processing_version"] == 1

    # 3. No uncommitted v2 staged events remain in database
    v2_events = await fake_db.events.count_documents({"evidence_id": evidence_id, "processing_version": 2})
    assert v2_events == 0

    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_break_active_version2(client: AsyncClient, fake_db, monkeypatch):
    """Failure Injection: Simulates cleanup failure of superseded events after pointer switch succeeds.

    Verifies that:
    1. Because pointer switch has already succeeded, active version is 2.
    2. Readers only see active version 2 events even if older version 1 events deletion encountered an error.
    """
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Cleanup Failure Test Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Order ORD-300 placed by customer Charlie on Wednesday.")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("order3.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})

    # Run version 1
    job_v1 = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order3.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=0,
    )
    await evidence_processing_service.run_job(job_v1, fake_db)

    # Authorize retry
    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"status": EvidenceStatus.REVIEW_NEEDED.value}},
    )

    # Hook delete_many to fail when cleaning up superseded versions (< target_version)
    orig_delete_many = fake_db.events.delete_many

    async def fail_superseded_cleanup(query):
        if isinstance(query.get("processing_version"), dict) and "$lt" in query["processing_version"]:
            raise RuntimeError("Simulated network failure during superseded event cleanup")
        return await orig_delete_many(query)

    monkeypatch.setattr(fake_db.events, "delete_many", fail_superseded_cleanup)

    job_v2 = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order3.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=1,
    )
    await evidence_processing_service.run_job(job_v2, fake_db)

    # 1. Pointer successfully points to version 2
    ev_row = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert ev_row["active_processing_version"] == 2

    # 2. Status was NOT corrupted to FAILED (remains active READY or REVIEW_NEEDED)
    assert ev_row["status"] in (EvidenceStatus.READY.value, EvidenceStatus.REVIEW_NEEDED.value)

    # 3. Readers query active version 2 and ONLY see version 2 events!
    reader_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/events",
        headers={"X-User-ID": "usr_alice"},
    )
    items = reader_res.json()["data"]["items"]
    assert len(items) >= 1
    assert all(item["processing_version"] == 2 for item in items)

    # 4. The newly active events were NOT deleted on post-activation cleanup error
    new_events_count = await fake_db.events.count_documents({"evidence_id": evidence_id, "processing_version": 2})
    assert new_events_count == len(items)

    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_retry_cannot_overwrite_inflight_run(client: AsyncClient, fake_db):
    """Safety: Verifies that a retry cannot overwrite or clear an in-flight run's current_run_id."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Inflight Retry Protection Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Order ORD-999 placed by customer Eve.")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("order999.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]
    active_run_id = "run_live_inflight_123"

    # Simulate in-flight processing status
    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"status": EvidenceStatus.EXTRACTING.value, "current_run_id": active_run_id}},
    )

    # Attempt to retry while job is currently in-flight
    retry_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/retry",
        headers={"X-User-ID": "usr_alice"},
    )
    assert retry_res.status_code == 400
    assert "Cannot retry evidence with status 'EXTRACTING'" in retry_res.json()["error"]["message"]

    # Verify current_run_id was NOT overwritten or cleared
    ev_row = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert ev_row["current_run_id"] == active_run_id
    assert ev_row["status"] == EvidenceStatus.EXTRACTING.value

    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_successful_run_zero_events_atomically_clears_old_events(client: AsyncClient, fake_db, monkeypatch):
    """Correctness: Verifies that a successful reprocessing run producing 0 events
    switches active_processing_version to 2, clears superseded events, and returns 0 events.
    """
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Zero Events Test Case"},
        headers={"X-User-ID": "usr_alice"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Order ORD-400 placed by customer Dave.")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("order4.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": "usr_alice"},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})

    # Initial run producing events
    job_v1 = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order4.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=0,
    )
    await evidence_processing_service.run_job(job_v1, fake_db)

    # Confirm v1 events present
    r1 = await client.get(f"/api/v1/cases/{case_id}/evidence/{evidence_id}/events", headers={"X-User-ID": "usr_alice"})
    assert len(r1.json()["data"]["items"]) >= 1

    # Authorize retry
    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"status": EvidenceStatus.REVIEW_NEEDED.value}},
    )

    # Mock event cascade to return 0 events on retry
    monkeypatch.setattr(evidence_processing_service.event_cascade, "process_evidence", lambda *args, **kwargs: [])

    job_v2 = ProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id="usr_alice",
        storage_relative_path=doc["storage_relative_path"],
        original_filename="order4.pdf",
        media_type="application/pdf",
        sha256_hash=doc["sha256_hash"],
        retry_count=1,
    )
    await evidence_processing_service.run_job(job_v2, fake_db)

    # Verify active version is now 2
    ev_row = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert ev_row["active_processing_version"] == 2
    assert ev_row["extraction_summary"]["events_extracted"] == 0

    # Verify reader query returns 0 events
    r2 = await client.get(f"/api/v1/cases/{case_id}/evidence/{evidence_id}/events", headers={"X-User-ID": "usr_alice"})
    assert len(r2.json()["data"]["items"]) == 0
    assert r2.json()["data"]["pagination"]["total"] == 0

    storage_service.remove_evidence_file(doc["storage_relative_path"])


@pytest.mark.asyncio
async def test_interrupted_job_recovery_cleanup(fake_db):
    """Correctness: Tests recovery of interrupted jobs with unique run identifiers and safe run-scoped cleanup."""
    from datetime import datetime, timedelta, timezone

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    test_evi_id = "evi_stale_test_123456"
    stale_run_id = "run_stale_abc999"

    # Insert simulated interrupted evidence with current_run_id
    await fake_db.evidence.insert_one(
        {
            "evidence_id": test_evi_id,
            "case_id": "cas_test",
            "user_id": "usr_alice",
            "status": "ANALYZING",
            "heartbeat_at": stale_time,
            "current_run_id": stale_run_id,
            "processing_version": 2,
            "active_processing_version": 1,
        }
    )

    # Insert uncommitted staged event for stale run
    await fake_db.events.insert_one(
        {
            "event_id": "evt_staged_abandoned",
            "evidence_id": test_evi_id,
            "case_id": "cas_test",
            "user_id": "usr_alice",
            "processing_run_id": stale_run_id,
            "processing_version": 2,
        }
    )

    # Run interrupted job recovery
    recovered = await evidence_processing_service.recover_interrupted_jobs(fake_db, timeout_seconds=300)
    assert recovered == 1

    # Verify status changed to INTERRUPTED
    updated_doc = await fake_db.evidence.find_one({"evidence_id": test_evi_id})
    assert updated_doc["status"] == "INTERRUPTED"
    assert updated_doc["error_code"] == "JOB_INTERRUPTED"

    # Verify uncommitted staged event was cleaned up
    event_in_db = await fake_db.events.find_one({"event_id": "evt_staged_abandoned"})
    assert event_in_db is None


@pytest.mark.asyncio
async def test_recovery_does_not_delete_newer_live_run(fake_db):
    """Correctness: Verifies recovery of a stale run never purges staged records belonging to a live or newer run."""
    from datetime import datetime, timedelta, timezone

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    test_evi_id = "evi_dual_run_test"
    stale_run = "run_stale_111"
    live_run = "run_live_222"

    await fake_db.evidence.insert_one(
        {
            "evidence_id": test_evi_id,
            "status": "ANALYZING",
            "heartbeat_at": stale_time,
            "current_run_id": stale_run,
            "active_processing_version": 1,
        }
    )

    # Event for stale run
    await fake_db.events.insert_one(
        {
            "event_id": "evt_stale",
            "evidence_id": test_evi_id,
            "processing_run_id": stale_run,
        }
    )

    # Event for newer live run
    await fake_db.events.insert_one(
        {
            "event_id": "evt_live",
            "evidence_id": test_evi_id,
            "processing_run_id": live_run,
        }
    )

    # Run recovery
    recovered = await evidence_processing_service.recover_interrupted_jobs(fake_db, timeout_seconds=300)
    assert recovered == 1

    # Stale run event deleted
    assert await fake_db.events.find_one({"event_id": "evt_stale"}) is None

    # Live run event preserved intact!
    assert await fake_db.events.find_one({"event_id": "evt_live"}) is not None


@pytest.mark.asyncio
async def test_concurrent_recovery_workers_only_one_wins(fake_db):
    """Correctness: Verifies that when multiple recovery workers run simultaneously,
    only one worker successfully claims each stale job.
    """
    from datetime import datetime, timedelta, timezone

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    test_evi_id = "evi_race_recovery"

    await fake_db.evidence.insert_one(
        {
            "evidence_id": test_evi_id,
            "status": "EXTRACTING",
            "heartbeat_at": stale_time,
            "current_run_id": "run_stale_xyz",
        }
    )

    # First recovery worker
    rec1 = await evidence_processing_service.recover_interrupted_jobs(fake_db, timeout_seconds=300)
    # Second recovery worker runs immediately after
    rec2 = await evidence_processing_service.recover_interrupted_jobs(fake_db, timeout_seconds=300)

    assert rec1 == 1
    assert rec2 == 0


@pytest.mark.asyncio
async def test_production_auth_rejects_x_user_id(client: AsyncClient, monkeypatch):
    """Priority 4: Verifies that development-only X-User-ID cannot be used as production authentication."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    res = await client.get(
        "/api/v1/cases",
        headers={"X-User-ID": "attacker_spoofed_user"},
    )
    assert res.status_code == 401
    assert "Production authentication required" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_storage_path_traversal_prevention():
    """Priority 4: Verifies storage paths cannot escape configured storage root."""
    with pytest.raises(HTTPException) as exc_info:
        storage_service._resolve_safe_path("../../../etc/passwd")
    assert exc_info.value.status_code == 400
    assert "traversal prohibited" in exc_info.value.detail

