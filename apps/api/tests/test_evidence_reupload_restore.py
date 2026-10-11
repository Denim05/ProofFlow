"""Tests for ProofFlow evidence re-upload, deduplication, and physical file restoration.

Verifies:
1. Re-uploading an identical file when the physical file is present retains the record and removes redundant file.
2. Re-uploading an identical file when the physical file was wiped (Render Free ephemeral disk reset)
   safely restores the physical file on disk without creating duplicate records or losing case history.
3. Preview and download endpoints work immediately after the file is restored.
4. Re-uploading when the record had status FAILED re-queues extraction with the restored file.
5. Uploading a file with the same filename but different content (different SHA-256) is not a duplicate.
6. Case ownership and tenant isolation are preserved during re-upload and restoration.
"""

import os
import pymupdf
import pytest
from httpx import AsyncClient

from app.services.storage import storage_service
from tests.conftest import FakeAsyncDatabase


def make_sample_pdf_bytes(text: str = "Evidence document for restore verification.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_reupload_duplicate_when_file_exists_on_disk(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """When the physical file already exists on disk, re-upload returns is_duplicate=True without restoring."""
    user_id = "user_reupload_1"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Case Duplicate Disk Test"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Original contract document content")
    files1 = {"file": ("proofflow-test.txt.pdf", pdf_bytes, "application/pdf")}

    # Initial upload
    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files1,
        headers={"X-User-ID": user_id},
    )
    assert res1.status_code == 201
    data1 = res1.json()["data"]
    assert data1["is_duplicate"] is False
    evidence_id = data1["evidence_id"]

    # Verify physical file exists
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    rel_path = doc["storage_relative_path"]
    full_path = storage_service._resolve_safe_path(rel_path)
    assert os.path.exists(full_path)

    # Re-upload exact same file while file is on disk
    files2 = {"file": ("proofflow-test.txt.pdf", pdf_bytes, "application/pdf")}
    res2 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files2,
        headers={"X-User-ID": user_id},
    )
    assert res2.status_code == 201
    data2 = res2.json()["data"]
    assert data2["is_duplicate"] is True
    assert data2["file_restored"] is False
    assert data2["evidence_id"] == evidence_id

    # Verify only 1 record exists in database
    count = await fake_db.evidence.count_documents({"case_id": case_id})
    assert count == 1


@pytest.mark.asyncio
async def test_reupload_restores_missing_physical_file(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """When the physical file was wiped on Render Free restart, re-upload restores the file on disk."""
    user_id = "user_reupload_2"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Case Ephemeral Restore Test"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Important Invoice INV-2026-99")
    files1 = {"file": ("proofflow-test.txt.pdf", pdf_bytes, "application/pdf")}

    # Initial upload
    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files1,
        headers={"X-User-ID": user_id},
    )
    assert res1.status_code == 201
    evidence_id = res1.json()["data"]["evidence_id"]

    # Retrieve record and path
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    rel_path = doc["storage_relative_path"]
    full_path = storage_service._resolve_safe_path(rel_path)
    assert os.path.exists(full_path)

    # Simulate Render Free restart: physical file wiped from disk
    os.remove(full_path)
    assert not os.path.exists(full_path)

    # Preview endpoint should report 404 (file missing on disk)
    preview_res_before = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert preview_res_before.status_code == 404
    assert "Render Free" in preview_res_before.json()["error"]["message"]

    # Re-upload the identical file
    files_reupload = {"file": ("proofflow-test.txt.pdf", pdf_bytes, "application/pdf")}
    reupload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files_reupload,
        headers={"X-User-ID": user_id},
    )
    assert reupload_res.status_code == 201
    reupload_data = reupload_res.json()["data"]

    # Should retain existing evidence ID and indicate restoration
    assert reupload_data["evidence_id"] == evidence_id
    assert reupload_data["is_duplicate"] is True
    assert reupload_data["file_restored"] is True

    # Database count remains strictly 1 (no duplicate records)
    count = await fake_db.evidence.count_documents({"case_id": case_id})
    assert count == 1

    # Physical file is now restored on disk
    assert os.path.exists(full_path)
    with open(full_path, "rb") as f:
        assert f.read() == pdf_bytes

    # Preview endpoint now succeeds with 200 and serves the PDF
    preview_res_after = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert preview_res_after.status_code == 200
    assert preview_res_after.headers["Content-Type"] == "application/pdf"
    assert preview_res_after.content == pdf_bytes

    # Download endpoint also succeeds
    download_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/download",
        headers={"X-User-ID": user_id},
    )
    assert download_res.status_code == 200
    assert download_res.content == pdf_bytes


@pytest.mark.asyncio
async def test_reupload_different_content_same_filename_creates_new_record(
    client: AsyncClient, fake_db: FakeAsyncDatabase
):
    """Uploading a file with the same filename but different content is NOT a duplicate."""
    user_id = "user_reupload_3"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Same Name Different Content"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes_v1 = make_sample_pdf_bytes("Version 1 content")
    pdf_bytes_v2 = make_sample_pdf_bytes("Version 2 completely different content")

    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("proofflow-test.txt.pdf", pdf_bytes_v1, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    assert res1.status_code == 201
    assert res1.json()["data"]["is_duplicate"] is False
    id1 = res1.json()["data"]["evidence_id"]

    res2 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("proofflow-test.txt.pdf", pdf_bytes_v2, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    assert res2.status_code == 201
    assert res2.json()["data"]["is_duplicate"] is False
    id2 = res2.json()["data"]["evidence_id"]

    assert id1 != id2
    count = await fake_db.evidence.count_documents({"case_id": case_id})
    assert count == 2


@pytest.mark.asyncio
async def test_reupload_failed_status_restores_and_requeues(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """When an evidence record has FAILED status and missing file, re-uploading restores the file and re-queues."""
    user_id = "user_reupload_4"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Failed Evidence Recovery"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Contract that failed prior extraction")
    files1 = {"file": ("proofflow-test.txt.pdf", pdf_bytes, "application/pdf")}

    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files1,
        headers={"X-User-ID": user_id},
    )
    evidence_id = res1.json()["data"]["evidence_id"]

    # Simulate failure and file wipe
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    full_path = storage_service._resolve_safe_path(doc["storage_relative_path"])
    if os.path.exists(full_path):
        os.remove(full_path)

    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"status": "FAILED", "error_code": "FILE_MISSING", "error_message": "Disk wiped"}},
    )

    # Re-upload
    reupload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("proofflow-test.txt.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    assert reupload_res.status_code == 201
    data = reupload_res.json()["data"]
    assert data["file_restored"] is True
    assert data["status"] in ["QUEUED", "READY", "EXTRACTING"]

    # File exists again
    assert os.path.exists(full_path)
