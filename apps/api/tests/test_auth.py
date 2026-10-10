from datetime import datetime, timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
import jwt
from jwt.exceptions import PyJWKClientError
import pytest
from app.core.auth import verify_clerk_token
from app.core.config import Settings, settings

# Generate deterministic RSA 2048-bit test keys
TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()

OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PUBLIC_KEY = OTHER_PRIVATE_KEY.public_key()

TEST_KEY_ID = "test-rsa-key-1"
TEST_ISSUER = "https://clerk.test.example.com"
TEST_AUDIENCE = "proofflow-api"
TEST_AZP = "http://localhost:3000"


@pytest.fixture(autouse=True)
def setup_auth_test_settings(monkeypatch):
    """Ensure tests in test_auth.py use mock Clerk settings regardless of local .env files."""
    monkeypatch.setattr(settings, "CLERK_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "CLERK_JWKS_URL", f"{TEST_ISSUER}/.well-known/jwks.json")
    monkeypatch.setattr(settings, "CLERK_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(settings, "CLERK_AUTHORIZED_PARTIES", [TEST_AZP])


class MockPyJWK:
    def __init__(self, key, key_id=TEST_KEY_ID):
        self.key = key
        self.key_id = key_id


class MockJWKClient:
    def __init__(self, public_key=TEST_PUBLIC_KEY, valid_kid=TEST_KEY_ID, fail_network=False):
        self.public_key = public_key
        self.valid_kid = valid_kid
        self.fail_network = fail_network

    def get_signing_key_from_jwt(self, token: str):
        if self.fail_network:
            raise PyJWKClientError("Network timeout connecting to JWKS provider")
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if kid != self.valid_kid:
            raise PyJWKClientError(f"Key ID '{kid}' not found in JWKS")
        return MockPyJWK(self.public_key, key_id=self.valid_kid)


def create_test_token(
    sub="usr_clerk_123",
    exp=2500000000,
    nbf=None,
    iss=TEST_ISSUER,
    aud=TEST_AUDIENCE,
    azp=TEST_AZP,
    kid=TEST_KEY_ID,
    algorithm="RS256",
    key=TEST_PRIVATE_KEY,
):
    payload = {"sub": sub, "exp": exp}
    if nbf is not None:
        payload["nbf"] = nbf
    if iss is not None:
        payload["iss"] = iss
    if aud is not None:
        payload["aud"] = aud
    if azp is not None:
        payload["azp"] = azp

    headers = {}
    if kid is not None:
        headers["kid"] = kid

    return jwt.encode(payload, key, algorithm=algorithm, headers=headers)


# ---------------------------------------------------------------------------
# Unit Tests for Token Verification Module (app.core.auth)
# ---------------------------------------------------------------------------


def test_verify_valid_token():
    """Verify that a compliant RS256 token signed by the trusted key passes validation."""
    token = create_test_token()
    mock_client = MockJWKClient()
    claims = verify_clerk_token(
        token,
        jwk_client=mock_client,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        authorized_parties=[TEST_AZP],
    )
    assert claims["sub"] == "usr_clerk_123"
    assert claims["iss"] == TEST_ISSUER


def test_verify_token_missing_or_empty():
    """Verify that missing or empty token string raises 401."""
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token("", jwk_client=mock_client)
    assert exc_info.value.status_code == 401
    assert "missing or empty" in exc_info.value.detail


def test_verify_token_malformed_header():
    """Verify that completely malformed token strings raise 401."""
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token("not-a-valid-jwt-token", jwk_client=mock_client)
    assert exc_info.value.status_code == 401


def test_verify_token_disallowed_algorithm():
    """Verify that tokens using disallowed algorithms (e.g. HS256, none) are strictly rejected."""
    # Create HMAC token
    hs_token = jwt.encode(
        {"sub": "attacker", "exp": 2500000000},
        b"a_secure_hmac_key_at_least_32_bytes_long",
        algorithm="HS256",
    )
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(hs_token, jwk_client=mock_client)
    assert exc_info.value.status_code == 401
    assert "algorithm not allowed" in exc_info.value.detail


def test_verify_token_invalid_signature():
    """Verify that tokens signed by an untrusted private key fail signature verification."""
    # Signed by OTHER_PRIVATE_KEY but verified against TEST_PUBLIC_KEY
    token = create_test_token(key=OTHER_PRIVATE_KEY)
    mock_client = MockJWKClient(public_key=TEST_PUBLIC_KEY)
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(token, jwk_client=mock_client, issuer=TEST_ISSUER)
    assert exc_info.value.status_code == 401
    assert "signature verification failed" in exc_info.value.detail


def test_verify_token_expired():
    """Verify that an expired token (exp in the past) raises 401."""
    past_timestamp = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    token = create_test_token(exp=past_timestamp)
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(token, jwk_client=mock_client, issuer=TEST_ISSUER)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail


def test_verify_token_immature_nbf():
    """Verify that a token with a future nbf claim raises 401."""
    future_timestamp = int(datetime(2040, 1, 1, tzinfo=timezone.utc).timestamp())
    token = create_test_token(nbf=future_timestamp)
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(token, jwk_client=mock_client, issuer=TEST_ISSUER)
    assert exc_info.value.status_code == 401
    assert "not yet valid" in exc_info.value.detail


def test_verify_token_wrong_issuer():
    """Verify that a token with an issuer mismatch raises 401."""
    token = create_test_token(iss="https://malicious.issuer.com")
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(token, jwk_client=mock_client, issuer=TEST_ISSUER)
    assert exc_info.value.status_code == 401
    assert "issuer is invalid" in exc_info.value.detail


def test_verify_token_wrong_audience():
    """Verify that a token with an audience mismatch raises 401."""
    token = create_test_token(aud="unrelated-api")
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(
            token, jwk_client=mock_client, issuer=TEST_ISSUER, audience=TEST_AUDIENCE
        )
    assert exc_info.value.status_code == 401
    assert "audience is invalid" in exc_info.value.detail


def test_verify_token_wrong_authorized_party():
    """Verify that a token with an unpermitted authorized party (azp) raises 401."""
    token = create_test_token(azp="http://evil-site.com")
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(
            token,
            jwk_client=mock_client,
            issuer=TEST_ISSUER,
            authorized_parties=["http://localhost:3000"],
        )
    assert exc_info.value.status_code == 401
    assert "authorized party (azp) is not permitted" in exc_info.value.detail


def test_verify_token_missing_or_empty_subject():
    """Verify that tokens without a subject claim or with an empty string raise 401."""
    token_empty_sub = create_test_token(sub="   ")
    mock_client = MockJWKClient()
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(token_empty_sub, jwk_client=mock_client, issuer=TEST_ISSUER)
    assert exc_info.value.status_code == 401
    assert "invalid or empty subject" in exc_info.value.detail


def test_verify_token_unknown_kid():
    """Verify that an unknown key ID in the token header raises 401."""
    token = create_test_token(kid="unknown-key-999")
    mock_client = MockJWKClient(valid_kid=TEST_KEY_ID)
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(token, jwk_client=mock_client, issuer=TEST_ISSUER)
    assert exc_info.value.status_code == 401
    assert "key ID not found" in exc_info.value.detail


def test_verify_token_jwks_network_failure():
    """Verify that network or provider errors during JWKS fetch fail closed with 401 without leaking internal details."""
    token = create_test_token()
    mock_client = MockJWKClient(fail_network=True)
    with pytest.raises(HTTPException) as exc_info:
        verify_clerk_token(token, jwk_client=mock_client, issuer=TEST_ISSUER)
    assert exc_info.value.status_code == 401
    assert "JWKS endpoint unavailable" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Integration Tests: Dependency & Route Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_with_valid_bearer_token(client):
    """Verify that API endpoints authenticate successfully with a valid RS256 Bearer token."""
    token = create_test_token(sub="usr_authenticated_bob")
    mock_client = MockJWKClient()

    with patch("app.core.auth.get_jwk_client", return_value=mock_client):
        # Create a case as Bob
        resp = await client.post(
            "/api/v1/cases",
            json={"title": "Bob Secure Case"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["user_id"] == "usr_authenticated_bob"


@pytest.mark.asyncio
async def test_api_x_user_id_cannot_override_bearer_token(client):
    """Verify that an attacker cannot spoof identity using X-User-ID when presenting a Bearer token."""
    token = create_test_token(sub="usr_real_alice")
    mock_client = MockJWKClient()

    with patch("app.core.auth.get_jwk_client", return_value=mock_client):
        # Pass token for Alice, but maliciously set X-User-ID to Bob
        resp = await client.post(
            "/api/v1/cases",
            json={"title": "Identity Spoof Attempt"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-User-ID": "usr_spoofed_bob",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        # The stored case MUST belong to Alice (the token sub), not Bob!
        assert data["user_id"] == "usr_real_alice"


@pytest.mark.asyncio
async def test_api_malformed_authorization_header(client):
    """Verify that malformed Authorization headers (not 'Bearer <token>') return 401."""
    resp = await client.get(
        "/api/v1/cases",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "expected format 'Bearer <token>'" in body["error"]["message"]


@pytest.mark.asyncio
async def test_api_dev_bypass_disabled_rejects_without_token(client):
    """Verify that when ALLOW_DEV_AUTH_BYPASS is False, requests without Bearer token are rejected with 401."""
    with patch.object(settings, "ALLOW_DEV_AUTH_BYPASS", False):
        resp = await client.get("/api/v1/cases", headers={"X-User-ID": "usr_alice"})
        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert "missing Bearer token" in body["error"]["message"]


@pytest.mark.asyncio
async def test_api_cross_user_isolation_with_tokens(client):
    """Verify that User B presenting a valid token cannot access User A's case."""
    token_alice = create_test_token(sub="usr_alice_token")
    token_bob = create_test_token(sub="usr_bob_token")
    mock_client = MockJWKClient()

    with patch("app.core.auth.get_jwk_client", return_value=mock_client):
        # Alice creates a case
        create_res = await client.post(
            "/api/v1/cases",
            json={"title": "Alice Private Investigation"},
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        case_id = create_res.json()["data"]["case_id"]

        # Bob attempts to get Alice's case -> 404 Not Found (non-disclosing)
        get_res = await client.get(
            f"/api/v1/cases/{case_id}",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert get_res.status_code == 404
        assert "was not found" in get_res.json()["error"]["message"]

        # Bob attempts to get Alice's findings -> 404 Not Found
        findings_res = await client.get(
            f"/api/v1/cases/{case_id}/findings",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert findings_res.status_code == 404
