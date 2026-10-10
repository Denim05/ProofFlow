"""Tests for in-memory rate limiting on evidence uploads and PDF exports."""

import io
import time
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
import pymupdf

from app.core.config import settings
from app.core.rate_limiter import InMemoryRateLimiter, rate_limiter, resolve_client_ip
from tests.conftest import FakeAsyncDatabase


def make_dummy_pdf(text: str = "Rate Limit Test PDF") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    b = doc.tobytes()
    doc.close()
    return b


def test_rate_limiter_allows_requests_within_quota():
    """Requests under max_requests within window must succeed."""
    current_time = 1000.0
    limiter = InMemoryRateLimiter(time_provider=lambda: current_time)

    for _ in range(5):
        limiter.check(action="test_action", user_id="user_1", max_requests=5, window_seconds=60)


def test_rate_limiter_exceeded_raises_429():
    """Request exceeding max_requests must raise HTTPException 429 with Retry-After header."""
    current_time = 1000.0
    limiter = InMemoryRateLimiter(time_provider=lambda: current_time)

    for _ in range(3):
        limiter.check(action="test_action", user_id="user_1", max_requests=3, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check(action="test_action", user_id="user_1", max_requests=3, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers
    assert int(exc_info.value.headers["Retry-After"]) >= 1


def test_rate_limiter_user_identity_isolation():
    """Exhausting quota for User A must not impact User B."""
    current_time = 1000.0
    limiter = InMemoryRateLimiter(time_provider=lambda: current_time)

    # Exhaust user_a limit
    for _ in range(2):
        limiter.check(action="upload", user_id="user_a", max_requests=2, window_seconds=60)

    with pytest.raises(HTTPException):
        limiter.check(action="upload", user_id="user_a", max_requests=2, window_seconds=60)

    # user_b should still have their full quota
    limiter.check(action="upload", user_id="user_b", max_requests=2, window_seconds=60)
    limiter.check(action="upload", user_id="user_b", max_requests=2, window_seconds=60)


def test_rate_limiter_sliding_window_expiration_without_sleep():
    """Advancing clock beyond window_seconds resets the quota deterministically."""
    clock_state = {"time": 1000.0}
    limiter = InMemoryRateLimiter(time_provider=lambda: clock_state["time"])

    # Exhaust limit of 2 requests
    limiter.check(action="export", user_id="user_1", max_requests=2, window_seconds=60)
    limiter.check(action="export", user_id="user_1", max_requests=2, window_seconds=60)

    with pytest.raises(HTTPException):
        limiter.check(action="export", user_id="user_1", max_requests=2, window_seconds=60)

    # Advance clock by 61 seconds (past window)
    clock_state["time"] += 61.0

    # Quota is now replenished
    limiter.check(action="export", user_id="user_1", max_requests=2, window_seconds=60)


class DummyRequest:
    def __init__(self, client_host: str, headers: dict = None):
        class DummyClient:
            def __init__(self, host: str):
                self.host = host

        self.client = DummyClient(client_host)
        self.headers = headers or {}


def test_resolve_client_ip_with_untrusted_client():
    """X-Forwarded-For is ignored if direct client is not in TRUSTED_PROXIES."""
    req = DummyRequest("203.0.113.5", {"x-forwarded-for": "198.51.100.99"})
    ip = resolve_client_ip(req, trusted_proxies=["10.0.0.1"])
    assert ip == "203.0.113.5"


def test_resolve_client_ip_with_trusted_proxy():
    """X-Forwarded-For is honored when direct client is in TRUSTED_PROXIES."""
    req = DummyRequest("10.0.0.1", {"x-forwarded-for": "198.51.100.99, 10.0.0.2"})
    ip = resolve_client_ip(req, trusted_proxies=["10.0.0.1"])
    assert ip == "198.51.100.99"


@pytest.mark.asyncio
async def test_evidence_upload_endpoint_rate_limiting(client: AsyncClient, fake_db: FakeAsyncDatabase, monkeypatch):
    """POST /evidence returns 429 when upload quota is exceeded, isolating users."""
    rate_limiter.reset()
    user_primary = "tester_upload_rl_1"
    user_secondary = "tester_upload_rl_2"
    case_id = "case_upload_rl_test"

    # Set temporary low limit for testing
    monkeypatch.setattr(settings, "RATE_LIMIT_EVIDENCE_UPLOAD_PER_MINUTE", 2)

    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_primary,
        "title": "Rate Limit Case",
        "status": "EMPTY",
        "evidence_count": 0,
        "tags": [],
    })

    pdf_bytes = make_dummy_pdf("Dummy PO Content")

    # Upload 1: Allowed
    res1 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("doc1.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_primary},
    )
    assert res1.status_code == 201

    # Upload 2: Allowed
    res2 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("doc2.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_primary},
    )
    assert res2.status_code == 201

    # Upload 3: Exceeded -> 429
    res3 = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"file": ("doc3.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_primary},
    )
    assert res3.status_code == 429
    err = res3.json()["error"]
    assert err["code"] == "TOO_MANY_REQUESTS"
    assert "Rate limit exceeded" in err["message"]
    assert "Retry-After" in res3.headers

    # Other user is not rate-limited (identity isolation)
    other_case_id = "case_upload_other_test"
    await fake_db.cases.insert_one({
        "case_id": other_case_id,
        "user_id": user_secondary,
        "title": "Other User Case",
        "status": "EMPTY",
        "evidence_count": 0,
        "tags": [],
    })
    res_other = await client.post(
        f"/api/v1/cases/{other_case_id}/evidence",
        files={"file": ("doc1.pdf", pdf_bytes, "application/pdf")},
        headers={"X-User-ID": user_secondary},
    )
    assert res_other.status_code == 201


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected_with_401_before_rate_limit(client: AsyncClient, monkeypatch):
    """Unauthenticated requests must fail with 401 and not consume or be blocked by rate limits."""
    rate_limiter.reset()
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "RATE_LIMIT_EVIDENCE_UPLOAD_PER_MINUTE", 1)

    pdf_bytes = make_dummy_pdf("Dummy PDF")

    # Request without token
    res = await client.post(
        "/api/v1/cases/case_any/evidence",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_pdf_export_endpoint_rate_limiting(client: AsyncClient, fake_db: FakeAsyncDatabase, monkeypatch):
    """GET /export/pdf returns 429 when export quota is exceeded."""
    rate_limiter.reset()
    user_id = "tester_export_rl"
    case_id = "case_export_rl_test"

    monkeypatch.setattr(settings, "RATE_LIMIT_DOSSIER_PDF_PER_MINUTE", 2)

    from datetime import datetime, timezone

    await fake_db.cases.insert_one({
        "case_id": case_id,
        "user_id": user_id,
        "title": "Export RL Case",
        "status": "READY",
        "evidence_count": 0,
        "tags": [],
        "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 1, 10, 5, 0, tzinfo=timezone.utc),
    })

    # Export 1: 200
    res1 = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": user_id})
    assert res1.status_code == 200, f"res1 failed: {res1.text}"

    # Export 2: 200
    res2 = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": user_id})
    assert res2.status_code == 200

    # Export 3: 429
    res3 = await client.get(f"/api/v1/cases/{case_id}/export/pdf", headers={"X-User-ID": user_id})
    assert res3.status_code == 429
    assert res3.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    assert "Retry-After" in res3.headers
