"""Regression tests for cross-filesystem / cross-device evidence promotion.

Reproduces and verifies resolution of:
    OSError: [Errno 18] Invalid cross-device link
which occurs when temp_root and storage_root reside on separate filesystems/mounts
(e.g., persistent disk mount at /app/storage/evidence and rootfs at /app/storage/temp).
"""

import errno
import hashlib
import io
import os
import shutil
import tempfile
import pytest
from fastapi import UploadFile
from httpx import AsyncClient

from app.services.storage import LocalStorageService, storage_service
from app.models.evidence import EvidenceStatus


def make_sample_pdf_bytes(text: str = "Test document for cross-device promotion verification.") -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def isolated_storage():
    """Provides an isolated LocalStorageService with separate temporary directories."""
    base_dir = tempfile.mkdtemp(prefix="proofflow_cross_device_test_")
    evidence_dir = os.path.join(base_dir, "evidence")
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(evidence_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    service = LocalStorageService()
    service.storage_root = os.path.abspath(evidence_dir)
    service.temp_root = os.path.abspath(temp_dir)

    yield service, temp_dir, evidence_dir

    shutil.rmtree(base_dir, ignore_errors=True)


def test_promote_same_filesystem_direct(isolated_storage):
    """Verifies that same-filesystem promotions succeed directly via atomic os.replace."""
    service, temp_dir, evidence_dir = isolated_storage

    temp_path = os.path.join(temp_dir, "test_file.tmp")
    with open(temp_path, "wb") as f:
        f.write(b"same-filesystem payload")

    final_path = os.path.join(evidence_dir, "case_1", "ev_1.bin")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)

    service._promote_temp_to_final(temp_path, final_path)

    assert os.path.exists(final_path)
    assert not os.path.exists(temp_path)
    with open(final_path, "rb") as f:
        assert f.read() == b"same-filesystem payload"


def test_promote_cross_filesystem_fallback_success(isolated_storage, monkeypatch):
    """Verifies that an EXDEV (Errno 18) error triggers the atomic two-stage promotion."""
    service, temp_dir, evidence_dir = isolated_storage

    content = b"cross-device payload bytes 12345"
    temp_path = os.path.join(temp_dir, "source_upload.tmp")
    with open(temp_path, "wb") as f:
        f.write(content)

    final_path = os.path.join(evidence_dir, "case_2", "ev_2.bin")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)

    original_replace = os.replace
    replace_calls = []

    def mock_replace(src, dst):
        replace_calls.append((src, dst))
        # First call attempting cross-device move between temp_dir and evidence_dir
        if src == temp_path and dst == final_path:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        # Subsequent call within the destination filesystem should succeed
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    service._promote_temp_to_final(temp_path, final_path)

    # Final file must exist with exact contents
    assert os.path.exists(final_path)
    with open(final_path, "rb") as f:
        assert f.read() == content

    # Exactly 2 calls to os.replace: initial failed EXDEV, then successful atomic rename
    assert len(replace_calls) == 2
    assert replace_calls[0] == (temp_path, final_path)
    assert replace_calls[1][1] == final_path
    # Intermediate destination temp file must be cleaned up / renamed away
    assert not os.path.exists(replace_calls[1][0])


def test_promote_cross_filesystem_failure_cleans_destination_temp(isolated_storage, monkeypatch):
    """Verifies that if copy fails midway, the destination temp file is deleted and final is not created."""
    service, temp_dir, evidence_dir = isolated_storage

    temp_path = os.path.join(temp_dir, "corrupt_source.tmp")
    with open(temp_path, "wb") as f:
        f.write(b"data to fail")

    final_path = os.path.join(evidence_dir, "case_fail", "ev_fail.bin")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)

    def mock_replace(src, dst):
        if src == temp_path:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return os.replace(src, dst)

    def mock_copyfileobj(f_src, f_dst, length=65536):
        # Simulate disk write failure during copy
        f_dst.write(b"partial bytes")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", mock_replace)
    monkeypatch.setattr(shutil, "copyfileobj", mock_copyfileobj)

    with pytest.raises(OSError, match="No space left on device"):
        service._promote_temp_to_final(temp_path, final_path)

    # Destination final must not exist
    assert not os.path.exists(final_path)

    # No leftover .tmp files in case_fail directory
    case_dir = os.path.dirname(final_path)
    temp_files_in_dest = [f for f in os.listdir(case_dir) if f.endswith(".tmp")]
    assert temp_files_in_dest == []


def test_promote_non_cross_device_error_reraised(isolated_storage, monkeypatch):
    """Verifies that standard filesystem errors (e.g., EACCES) are immediately re-raised."""
    service, temp_dir, evidence_dir = isolated_storage

    temp_path = os.path.join(temp_dir, "perm_test.tmp")
    with open(temp_path, "wb") as f:
        f.write(b"permission test payload")

    final_path = os.path.join(evidence_dir, "case_perm", "ev_perm.bin")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)

    def mock_replace(src, dst):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(OSError, match="Permission denied"):
        service._promote_temp_to_final(temp_path, final_path)

    assert not os.path.exists(final_path)


@pytest.mark.asyncio
async def test_save_upload_stream_handles_cross_device_link(isolated_storage, monkeypatch):
    """End-to-end unit test: save_upload_stream recovers from EXDEV and preserves hash and cleanup."""
    service, temp_dir, evidence_dir = isolated_storage

    pdf_bytes = make_sample_pdf_bytes("Cross-device upload stream test content.")
    expected_hash = hashlib.sha256(pdf_bytes).hexdigest()

    upload_file = UploadFile(
        file=io.BytesIO(pdf_bytes),
        filename="order_cross_device.pdf",
        headers={"content-type": "application/pdf"},
    )

    original_replace = os.replace
    exdev_triggered = False

    def mock_replace(src, dst):
        nonlocal exdev_triggered
        # Trigger EXDEV when trying to move from temp_dir to evidence_dir
        if temp_dir in src and evidence_dir in dst:
            exdev_triggered = True
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    rel_path, media_type, file_size, sha256_hash = await service.save_upload_stream(
        upload_file=upload_file,
        case_id="case_cd_123",
        evidence_id="ev_cd_456",
    )

    assert exdev_triggered is True
    assert media_type == "application/pdf"
    assert file_size == len(pdf_bytes)
    assert sha256_hash == expected_hash

    # Final file is stored correctly and readable
    full_path = os.path.join(evidence_dir, rel_path)
    assert os.path.exists(full_path)
    with open(full_path, "rb") as f:
        assert f.read() == pdf_bytes

    # Source temp file in temp_root must be cleaned up
    assert os.listdir(temp_dir) == []

    # Destination directory must contain only the final .bin file
    case_dir = os.path.dirname(full_path)
    assert os.listdir(case_dir) == ["ev_cd_456.bin"]


@pytest.mark.asyncio
async def test_api_upload_evidence_cross_device_regression(client: AsyncClient, fake_db, monkeypatch):
    """Full API regression test verifying evidence endpoint succeeds under cross-device conditions."""
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Cross Device API Case"},
        headers={"X-User-ID": "usr_cross_dev"},
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Testing API route under Errno 18 cross-device link.")
    files = {"file": ("invoice.pdf", pdf_bytes, "application/pdf")}

    original_replace = os.replace
    exdev_count = 0

    def mock_replace(src, dst):
        nonlocal exdev_count
        if storage_service.temp_root in src and storage_service.storage_root in dst:
            exdev_count += 1
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files=files,
        headers={"X-User-ID": "usr_cross_dev"},
    )

    assert upload_res.status_code == 201
    assert exdev_count >= 1

    upload_data = upload_res.json()["data"]
    assert upload_data["status"] == EvidenceStatus.QUEUED.value
    assert upload_data["file_size_bytes"] == len(pdf_bytes)
    assert upload_data["media_type"] == "application/pdf"

    # Verify database document
    evidence_id = upload_data["evidence_id"]
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    assert doc is not None
    assert doc["sha256_hash"] == hashlib.sha256(pdf_bytes).hexdigest()

    # Verify stored file content via storage_service
    stored_bytes = storage_service.read_evidence_bytes(doc["storage_relative_path"])
    assert stored_bytes == pdf_bytes

    # Cleanup
    storage_service.remove_evidence_file(doc["storage_relative_path"])
