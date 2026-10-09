import logging
from typing import Any, Dict, List, Optional
import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    PyJWKClientError,
    PyJWKError,
    PyJWTError,
)
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level cached JWKS client instance
_cached_jwk_client: Optional[jwt.PyJWKClient] = None
_cached_jwks_url: Optional[str] = None


def get_jwk_client(jwks_url: Optional[str] = None) -> jwt.PyJWKClient:
    """Returns a singleton or configured PyJWKClient instance with bounded caching."""
    global _cached_jwk_client, _cached_jwks_url

    target_url = jwks_url or settings.CLERK_JWKS_URL
    if not target_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service configuration error: CLERK_JWKS_URL is missing.",
        )

    if _cached_jwk_client is not None and _cached_jwks_url == target_url:
        return _cached_jwk_client

    _cached_jwk_client = jwt.PyJWKClient(
        target_url,
        cache_keys=True,
        max_cached_keys=16,
        cache_jwk_set=True,
        lifespan=settings.AUTH_JWKS_CACHE_TTL_SECONDS,
        timeout=settings.AUTH_JWKS_TIMEOUT_SECONDS,
    )
    _cached_jwks_url = target_url
    return _cached_jwk_client


def verify_clerk_token(
    token: str,
    jwk_client: Optional[jwt.PyJWKClient] = None,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
    authorized_parties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Cryptographically verifies a Clerk-issued RS256 Bearer JWT.

    Enforces:
    - RS256 algorithm strictly
    - Cryptographic signature against trusted JWKS
    - Expiration (exp) and Not-Before (nbf)
    - Issuer match (iss)
    - Audience match (aud) if configured
    - Authorized party (azp) if configured
    - Non-empty subject (sub)

    Returns:
        Dict[str, Any]: Verified claims dictionary.

    Raises:
        HTTPException(401): If token is invalid, expired, malformed, or untrusted.
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: bearer token is missing or empty.",
        )

    token = token.strip()

    # 1. Enforce RS256 explicitly from header inspection
    try:
        unverified_header = jwt.get_unverified_header(token)
    except DecodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: malformed token header.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: unable to decode header.",
        )

    algorithm = unverified_header.get("alg")
    if algorithm != "RS256":
        logger.warning("Rejected token with disallowed algorithm: %s", algorithm)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: algorithm not allowed. Only RS256 is permitted.",
        )

    # 2. Retrieve signing key from JWKS
    client = jwk_client or get_jwk_client()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except (PyJWKClientError, PyJWKError) as err:
        logger.warning("JWKS key resolution failed: %s", str(err))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: key ID not found or JWKS endpoint unavailable.",
        )
    except Exception as err:
        logger.warning("Unexpected error during key resolution: %s", str(err))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed: unable to resolve trusted public key.",
        )

    # 3. Configure strict decode options
    expected_issuer = issuer or settings.CLERK_ISSUER
    expected_audience = audience if audience is not None else settings.CLERK_AUDIENCE
    expected_azp = (
        authorized_parties
        if authorized_parties is not None
        else (
            settings.CLERK_AUTHORIZED_PARTIES
            if isinstance(settings.CLERK_AUTHORIZED_PARTIES, list)
            else [settings.CLERK_AUTHORIZED_PARTIES]
            if settings.CLERK_AUTHORIZED_PARTIES
            else []
        )
    )

    decode_options: Dict[str, Any] = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_nbf": True,
        "require": ["exp", "sub"],
    }
    decode_kwargs: Dict[str, Any] = {
        "key": signing_key.key,
        "algorithms": ["RS256"],
        "options": decode_options,
    }

    if expected_issuer:
        decode_options["verify_iss"] = True
        decode_options["require"].append("iss")
        decode_kwargs["issuer"] = expected_issuer
    else:
        decode_options["verify_iss"] = False

    if expected_audience:
        decode_options["verify_aud"] = True
        decode_kwargs["audience"] = expected_audience
    else:
        decode_options["verify_aud"] = False

    # 4. Verify cryptographic signature and claims
    try:
        claims = jwt.decode(token, **decode_kwargs)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
        )
    except ImmatureSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is not yet valid (nbf).",
        )
    except InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token issuer is invalid.",
        )
    except InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token audience is invalid.",
        )
    except InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token signature verification failed.",
        )
    except DecodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is malformed.",
        )
    except PyJWTError as err:
        logger.warning("Token verification failed with PyJWTError: %s", str(err))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is invalid.",
        )

    # 5. Validate authorized party (azp) if configured
    if expected_azp:
        token_azp = claims.get("azp")
        if not token_azp or token_azp not in expected_azp:
            logger.warning("Token azp '%s' not in authorized parties %s", token_azp, expected_azp)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token authorized party (azp) is not permitted.",
            )

    # 6. Validate subject (sub)
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str) or not sub.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token contains an invalid or empty subject (sub) claim.",
        )

    return claims
