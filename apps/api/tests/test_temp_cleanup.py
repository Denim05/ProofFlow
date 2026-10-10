"""Tests for safe abandoned temporary file cleanup."""

import os
import shutil
import tempfile
import time
import pytest

from app.core.config import settings
from app.services.storage import LocalStorageService
from app.main import app, lifespan


@pytest.fixture
def isolated_storage():
    """Sets up an isolated temporary storage environment for testing cleanup."""
    base_dir = tempfile.mkdtemp(prefix="proofflow_cleanup_test_")
    evidence_dir = os.path.join(base_dir, "evidence")
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(evidence_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    service = LocalStorageService()
    service.storage_root = os.path.abspath(evidence_dir)
    service.temp_root = os.path.abspath(temp_dir)

    yield service, temp_dir, evidence_dir

    shutil.rmtree(base_dir, ignore_errors=True)


def test_cleanup_deletes_stale_tmp_files(isolated_storage):
    """Files ending in .tmp older than max_age_seconds must be safely removed."""
    service, temp_dir, _ = isolated_storage
    now = 10000.0

    stale_file = os.path.join(temp_dir, "stale_upload.tmp")
    with open(stale_file, "wb") as f:
        f.write(b"abandoned upload content")

    # Set mtime to 2 hours ago (7200 seconds)
    os.utime(stale_file, (now - 7200, now - 7200))

    deleted = service.cleanup_abandoned_temp_files(max_age_seconds=3600, now=now)
    assert deleted == 1
    assert not os.path.exists(stale_file)


def test_cleanup_preserves_fresh_tmp_files(isolated_storage):
    """Files ending in .tmp newer than cutoff (e.g. active uploads) must not be deleted."""
    service, temp_dir, _ = isolated_storage
    now = 10000.0

    fresh_file = os.path.join(temp_dir, "active_upload.tmp")
    with open(fresh_file, "wb") as f:
        f.write(b"in-flight upload stream")

    # Set mtime to 5 minutes ago (300 seconds)
    os.utime(fresh_file, (now - 300, now - 300))

    deleted = service.cleanup_abandoned_temp_files(max_age_seconds=3600, now=now)
    assert deleted == 0
    assert os.path.exists(fresh_file)


def test_cleanup_preserves_active_in_flight_uploads_even_if_old(isolated_storage):
    """Files registered in _active_temp_paths must NEVER be deleted even if mtime is older than cutoff."""
    service, temp_dir, _ = isolated_storage
    now = 10000.0

    in_flight_file = os.path.join(temp_dir, "slow_client_upload.tmp")
    with open(in_flight_file, "wb") as f:
        f.write(b"streaming large document over slow link")

    # Set mtime to 3 hours ago (10800 seconds) - clearly past 1 hour cutoff
    os.utime(in_flight_file, (now - 10800, now - 10800))

    # Register as currently in-flight
    service._active_temp_paths.add(os.path.abspath(in_flight_file))

    deleted = service.cleanup_abandoned_temp_files(max_age_seconds=3600, now=now)
    assert deleted == 0
    assert os.path.exists(in_flight_file)

    # After active upload unregisters, next cleanup will safely prune it
    service._active_temp_paths.discard(os.path.abspath(in_flight_file))
    deleted_after = service.cleanup_abandoned_temp_files(max_age_seconds=3600, now=now)
    assert deleted_after == 1
    assert not os.path.exists(in_flight_file)


def test_cleanup_ignores_non_tmp_files_in_temp_directory(isolated_storage):
    """Non-.tmp files in temp_root (e.g. .gitkeep, metadata.json) must never be deleted even if old."""
    service, temp_dir, _ = isolated_storage
    now = 10000.0

    gitkeep_file = os.path.join(temp_dir, ".gitkeep")
    with open(gitkeep_file, "w") as f:
        f.write("")
    os.utime(gitkeep_file, (now - 7200, now - 7200))

    pdf_file = os.path.join(temp_dir, "sample.pdf")
    with open(pdf_file, "wb") as f:
        f.write(b"%PDF-1.4")
    os.utime(pdf_file, (now - 7200, now - 7200))

    deleted = service.cleanup_abandoned_temp_files(max_age_seconds=3600, now=now)
    assert deleted == 0
    assert os.path.exists(gitkeep_file)
    assert os.path.exists(pdf_file)


def test_cleanup_never_touches_permanent_evidence_files(isolated_storage):
    """Files in storage_root (permanent evidence) must never be inspected or deleted."""
    service, temp_dir, evidence_dir = isolated_storage
    now = 10000.0

    case_folder = os.path.join(evidence_dir, "case_12345")
    os.makedirs(case_folder, exist_ok=True)
    evidence_bin = os.path.join(case_folder, "evi_999.bin")
    with open(evidence_bin, "wb") as f:
        f.write(b"Permanent validated evidence data")
    os.utime(evidence_bin, (now - 7200, now - 7200))

    # Add one stale temp file
    stale_file = os.path.join(temp_dir, "orphaned.tmp")
    with open(stale_file, "wb") as f:
        f.write(b"orphaned data")
    os.utime(stale_file, (now - 7200, now - 7200))

    deleted = service.cleanup_abandoned_temp_files(max_age_seconds=3600, now=now)
    assert deleted == 1
    assert not os.path.exists(stale_file)
    assert os.path.exists(evidence_bin)


def test_cleanup_handles_missing_temp_directory(isolated_storage):
    """If temp_root directory does not exist, cleanup returns 0 gracefully without raising."""
    service, temp_dir, _ = isolated_storage
    shutil.rmtree(temp_dir, ignore_errors=True)

    deleted = service.cleanup_abandoned_temp_files(max_age_seconds=3600)
    assert deleted == 0


def test_cleanup_handles_filesystem_permission_errors_gracefully(isolated_storage, monkeypatch):
    """If os.remove raises an OSError, cleanup logs a warning and continues without crashing."""
    service, temp_dir, _ = isolated_storage
    now = 10000.0

    stale_file = os.path.join(temp_dir, "locked.tmp")
    with open(stale_file, "wb") as f:
        f.write(b"locked file")
    os.utime(stale_file, (now - 7200, now - 7200))

    def mock_remove_error(path):
        raise PermissionError("Access denied simulating file lock")

    monkeypatch.setattr(os, "remove", mock_remove_error)

    deleted = service.cleanup_abandoned_temp_files(max_age_seconds=3600, now=now)
    assert deleted == 0
    # Process continues without exception


@pytest.mark.asyncio
async def test_lifespan_invokes_temp_cleanup_without_crash(isolated_storage, monkeypatch):
    """Application lifespan startup should execute temp cleanup safely."""
    service, temp_dir, _ = isolated_storage
    monkeypatch.setattr("app.services.storage.storage_service", service)

    async with lifespan(app):
        pass
