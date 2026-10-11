"""Tests for secure evidence preview and download endpoints in ProofFlow.

Covers:
1. Authenticated PDF preview with safe inline Content-Disposition and application/pdf Content-Type.
2. Authenticated PDF download with attachment Content-Disposition.
3. Authenticated image preview with image/png Content-Type.
4. Authentication enforcement (unauthenticated requests rejected with 401).
5. Multi-tenant case authorization (cross-user requests return 404/403).
6. Case mismatch protection (evidence requested under wrong case_id returns 404).
7. Cross-case storage path tampering protection (forbidden 403).
8. Render Free ephemeral disk handling (clean 404 when file is missing from disk).
9. Filename sanitization against header injection and safe Unicode handling.
"""

import os
from unittest.mock import patch
import pymupdf
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.storage import storage_service
from tests.conftest import FakeAsyncDatabase


def make_sample_pdf_bytes(text: str = "Confidential Evidence Document - ProofFlow") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_sample_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.mark.asyncio
async def test_evidence_preview_pdf_headers(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies that previewing a PDF returns 200, application/pdf, and safe inline disposition."""
    user_id = "user_preview_alice"
    # 1. Create case
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Contract Dispute 2026"},
        headers={"X-User-ID": user_id},
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["data"]["case_id"]

    # 2. Upload valid PDF
    pdf_bytes = make_sample_pdf_bytes("Statement of Account #8820")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("statement_8820.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    assert upload_res.status_code == 201
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # 3. Call preview endpoint directly
    preview_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert preview_res.status_code == 200
    assert preview_res.headers["Content-Type"] == "application/pdf"
    assert "inline" in preview_res.headers["Content-Disposition"]
    assert "statement_8820.pdf" in preview_res.headers["Content-Disposition"]
    assert preview_res.headers["X-Content-Type-Options"] == "nosniff"
    assert "private" in preview_res.headers["Cache-Control"]
    assert preview_res.content == pdf_bytes

    # 4. Call download endpoint with ?inline=true
    download_inline_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/download?inline=true",
        headers={"X-User-ID": user_id},
    )
    assert download_inline_res.status_code == 200
    assert "inline" in download_inline_res.headers["Content-Disposition"]
    assert download_inline_res.content == pdf_bytes


@pytest.mark.asyncio
async def test_evidence_download_attachment_headers(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies that downloading returns attachment disposition."""
    user_id = "user_download_bob"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Procurement Audit"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Invoice #1001")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("invoice_1001.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Default download (inline=False)
    res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/download",
        headers={"X-User-ID": user_id},
    )
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "application/pdf"
    assert res.headers["Content-Disposition"].startswith("attachment;")
    assert "invoice_1001.pdf" in res.headers["Content-Disposition"]
    assert res.content == pdf_bytes


@pytest.mark.asyncio
async def test_evidence_preview_image(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies that image evidence can also be previewed with image MIME type."""
    user_id = "user_preview_img"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Photo Documentation"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    png_bytes = make_sample_png_bytes()
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("damaged_goods.png", png_bytes, "image/png")},
        headers={"X-User-ID": user_id},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "image/png"
    assert "inline" in res.headers["Content-Disposition"]
    assert res.content == png_bytes


@pytest.mark.asyncio
async def test_evidence_preview_unauthenticated_rejected(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies that requests without authentication token are strictly rejected."""
    # When dev auth bypass is False, request without Authorization token fails with 401
    with patch.object(settings, "ALLOW_DEV_AUTH_BYPASS", False):
        res = await client.get(
            "/api/v1/cases/case_nonexistent/evidence/evi_nonexistent/preview"
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_evidence_preview_case_ownership_isolated(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies that User B cannot preview User A's evidence."""
    user_a = "user_alice_isolated"
    user_b = "user_bob_isolated"

    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Alice Private Case"},
        headers={"X-User-ID": user_a},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Alice Secret Info")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("alice_secret.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_a},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Bob tries to access Alice's evidence
    bob_res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_b},
    )
    # verify_case_ownership returns 404 to avoid leaking case existence
    assert bob_res.status_code == 404


@pytest.mark.asyncio
async def test_evidence_preview_wrong_case_id(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies that requesting an evidence item under a different case returns 404."""
    user_id = "user_case_mismatch"

    case1 = await client.post(
        "/api/v1/cases",
        json={"title": "Case 1"},
        headers={"X-User-ID": user_id},
    )
    case1_id = case1.json()["data"]["case_id"]

    case2 = await client.post(
        "/api/v1/cases",
        json={"title": "Case 2"},
        headers={"X-User-ID": user_id},
    )
    case2_id = case2.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Doc under Case 1")
    upload_res = await client.post(
        f"/api/v1/cases/{case1_id}/evidence",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Request under Case 2
    res = await client.get(
        f"/api/v1/cases/{case2_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_evidence_preview_cross_case_path_tampering_blocked(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies that if storage_relative_path does not start with case_id/, it returns 403."""
    user_id = "user_tamper"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Tamper Test"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Tamper Test Doc")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Simulate tampered database record pointing to another directory
    await fake_db.evidence.update_one(
        {"evidence_id": evidence_id},
        {"$set": {"storage_relative_path": "other_case_999/fake.bin"}},
    )

    res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert res.status_code == 403
    assert "does not belong to the requested case" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_evidence_preview_missing_file_on_disk_render_free(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies graceful 404 handling when ephemeral disk file was purged after container restart."""
    user_id = "user_ephemeral"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Ephemeral Test"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    pdf_bytes = make_sample_pdf_bytes("Temporary storage doc")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("statement.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    # Delete the underlying file to simulate Render Free ephemeral restart
    doc = await fake_db.evidence.find_one({"evidence_id": evidence_id})
    rel_path = doc["storage_relative_path"]
    full_path = storage_service._resolve_safe_path(rel_path)
    if os.path.exists(full_path):
        os.remove(full_path)

    res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert res.status_code == 404
    assert "Render Free" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_evidence_preview_safe_filename_handling(client: AsyncClient, fake_db: FakeAsyncDatabase):
    """Verifies safe handling of filenames containing Unicode and characters that could cause header injection."""
    user_id = "user_safe_filename"
    case_res = await client.post(
        "/api/v1/cases",
        json={"title": "Filename Test"},
        headers={"X-User-ID": user_id},
    )
    case_id = case_res.json()["data"]["case_id"]

    # Filename with quotes, newlines, and unicode
    nasty_filename = 'report "2026"\r\nSpecial € & ©.pdf'
    pdf_bytes = make_sample_pdf_bytes("Unicode report")
    upload_res = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": (nasty_filename, pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_id},
    )
    evidence_id = upload_res.json()["data"]["evidence_id"]

    res = await client.get(
        f"/api/v1/cases/{case_id}/evidence/{evidence_id}/preview",
        headers={"X-User-ID": user_id},
    )
    assert res.status_code == 200
    disposition = res.headers["Content-Disposition"]
    # Check no raw newlines in headers
    assert "\r" not in disposition
    assert "\n" not in disposition
    # Check UTF-8 encoded parameter is present
    assert "filename*=UTF-8''" in disposition
