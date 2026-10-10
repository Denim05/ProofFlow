from unittest.mock import patch
import pytest
from httpx import AsyncClient
import pymupdf

from app.models.case import CaseStatus
from app.models.evidence import EvidenceStatus
from app.services.evidence_processor import (
    ProcessingJob,
    evidence_processing_service,
)
from app.services.storage import storage_service


def make_pdf(text: str = "Order ORD-1001 was delivered on 2026-10-07.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    b = doc.tobytes()
    doc.close()
    return b


@pytest.mark.asyncio
async def test_case_lifecycle_new_case_is_ready(client: AsyncClient, fake_db):
    """Empty cases should start in READY status and have 0 evidence count."""
    res = await client.post(
        "/api/v1/cases",
        json={"title": "Empty Dispute Case"},
        headers={"X-User-ID": "usr_test"},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["status"] == CaseStatus.READY.value
    assert data["evidence_count"] == 0


@pytest.mark.asyncio
async def test_case_lifecycle_upload_transitions_to_processing(client: AsyncClient, fake_db):
    """Uploading evidence must transition the case to PROCESSING before background processing completes."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Active Case"},
        headers={"X-User-ID": "usr_test"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_pdf()
    files = {"file": ("invoice.pdf", pdf_bytes, "application/pdf")}

    # Intercept BackgroundTasks so background worker doesn't run synchronously in test client
    with patch("fastapi.BackgroundTasks.add_task") as mock_add_task:
        upload_res = await client.post(
            f"/api/v1/cases/{case_id}/evidence",
            files=files,
            headers={"X-User-ID": "usr_test"},
        )
        assert upload_res.status_code == 201
        assert mock_add_task.called

    case_doc = await fake_db.cases.find_one({"case_id": case_id})
    assert case_doc["status"] == CaseStatus.PROCESSING.value


@pytest.mark.asyncio
async def test_case_lifecycle_job_completion_and_idempotency(client: AsyncClient, fake_db):
    """Verifies that job completion sets correct status and repeated runs are strictly idempotent."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Idempotent Case"},
        headers={"X-User-ID": "usr_test"},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_pdf("Order PF-1001 was delivered on 2026-10-07.")
    files = {"file": ("delivery.pdf", pdf_bytes, "application/pdf")}

    with patch("fastapi.BackgroundTasks.add_task"):
        upload_res = await client.post(
            f"/api/v1/cases/{case_id}/evidence",
            files=files,
            headers={"X-User-ID": "usr_test"},
        )
    evi_id = upload_res.json()["data"]["evidence_id"]

    # Retrieve stored evidence document
    evi_doc = await fake_db.evidence.find_one({"evidence_id": evi_id})

    job = ProcessingJob(
        evidence_id=evi_id,
        case_id=case_id,
        user_id="usr_test",
        storage_relative_path=evi_doc["storage_relative_path"],
        original_filename=evi_doc["original_filename"],
        media_type=evi_doc["media_type"],
        sha256_hash=evi_doc["sha256_hash"],
    )

    # First execution
    await evidence_processing_service.run_job(job, fake_db)

    case_doc = await fake_db.cases.find_one({"case_id": case_id})
    assert case_doc["evidence_count"] == 1
    assert case_doc["status"] in (CaseStatus.READY.value, CaseStatus.REVIEW_NEEDED.value)

    # Second execution (retry/reprocess)
    await fake_db.evidence.update_one(
        {"evidence_id": evi_id},
        {"$set": {"status": EvidenceStatus.QUEUED.value}},
    )
    job.retry_count = 1
    await evidence_processing_service.run_job(job, fake_db)

    # Evidence count must remain 1 (idempotent, no double counting)
    case_doc_after = await fake_db.cases.find_one({"case_id": case_id})
    assert case_doc_after["evidence_count"] == 1


@pytest.mark.asyncio
async def test_case_lifecycle_concurrent_evidence_processing(client: AsyncClient, fake_db):
    """Case must stay in PROCESSING until all evidence documents complete processing."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Multi-Evidence Case"},
        headers={"X-User-ID": "usr_test"},
    )
    case_id = case_res.json()["data"]["case_id"]

    # Upload two separate evidence items with BackgroundTasks deferred
    pdf_1 = make_pdf("Evidence 1 doc")
    pdf_2 = make_pdf("Evidence 2 doc")

    with patch("fastapi.BackgroundTasks.add_task"):
        up1 = await client.post(
            f"/api/v1/cases/{case_id}/evidence",
            files={"file": ("doc1.pdf", pdf_1, "application/pdf")},
            headers={"X-User-ID": "usr_test"},
        )
        up2 = await client.post(
            f"/api/v1/cases/{case_id}/evidence",
            files={"file": ("doc2.pdf", pdf_2, "application/pdf")},
            headers={"X-User-ID": "usr_test"},
        )
    evi1_id = up1.json()["data"]["evidence_id"]
    evi2_id = up2.json()["data"]["evidence_id"]

    evi1_doc = await fake_db.evidence.find_one({"evidence_id": evi1_id})
    evi2_doc = await fake_db.evidence.find_one({"evidence_id": evi2_id})

    job1 = ProcessingJob(
        evidence_id=evi1_id,
        case_id=case_id,
        user_id="usr_test",
        storage_relative_path=evi1_doc["storage_relative_path"],
        original_filename=evi1_doc["original_filename"],
        media_type=evi1_doc["media_type"],
        sha256_hash=evi1_doc["sha256_hash"],
    )
    job2 = ProcessingJob(
        evidence_id=evi2_id,
        case_id=case_id,
        user_id="usr_test",
        storage_relative_path=evi2_doc["storage_relative_path"],
        original_filename=evi2_doc["original_filename"],
        media_type=evi2_doc["media_type"],
        sha256_hash=evi2_doc["sha256_hash"],
    )

    # Complete job 1 only; job 2 is still in QUEUED
    await evidence_processing_service.run_job(job1, fake_db)

    # Since job 2 is still QUEUED, case should remain in PROCESSING
    case_after_job1 = await fake_db.cases.find_one({"case_id": case_id})
    assert case_after_job1["status"] == CaseStatus.PROCESSING.value
    assert case_after_job1["evidence_count"] == 2

    # Now complete job 2
    await evidence_processing_service.run_job(job2, fake_db)

    case_after_job2 = await fake_db.cases.find_one({"case_id": case_id})
    assert case_after_job2["status"] in (CaseStatus.READY.value, CaseStatus.REVIEW_NEEDED.value)
    assert case_after_job2["evidence_count"] == 2
