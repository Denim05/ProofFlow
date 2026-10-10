"""In-memory sliding-window rate limiter for ProofFlow API.

ARCHITECTURAL & PRODUCTION SCALING NOTE:
The rate limiter implemented here uses in-memory sliding-window log tracking.
In-memory rate limits are strictly process-local. They provide immediate protection
against single-node denial of service, burst file uploads, and runaway export jobs.
However, in a horizontally scaled production deployment with multiple API worker
processes or container replicas behind a load balancer, rate limit quotas are not
shared across instances. For multi-replica production environments, a centralized
distributed store (such as Redis with atomic sliding logs or token buckets) must
be integrated.
"""

from collections import defaultdict
import time
from typing import Callable, Dict, List, Optional
from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.dependencies import get_current_user_id
from app.core.logging import logger


def resolve_client_ip(request: Optional[Request], trusted_proxies: Optional[List[str]] = None) -> str:
    """Extracts the client IP, honoring X-Forwarded-For ONLY when behind configured trusted proxies."""
    if not request or not request.client:
        return "unknown"

    direct_ip = request.client.host
    proxies = trusted_proxies if trusted_proxies is not None else settings.TRUSTED_PROXIES

    if not proxies or direct_ip not in proxies:
        return direct_ip

    # Direct client is an explicitly trusted proxy; inspect X-Forwarded-For header
    forwarded_header = request.headers.get("x-forwarded-for")
    if forwarded_header:
        ips = [ip.strip() for ip in forwarded_header.split(",") if ip.strip()]
        if ips:
            return ips[0]

    return direct_ip


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter with configurable time provider for deterministic testing."""

    def __init__(self, time_provider: Optional[Callable[[], float]] = None):
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._time_provider = time_provider or time.time

    def set_time_provider(self, time_provider: Optional[Callable[[], float]]) -> None:
        """Injects a custom clock for deterministic testing."""
        self._time_provider = time_provider or time.time

    def check(
        self,
        action: str,
        user_id: Optional[str] = None,
        request: Optional[Request] = None,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        """Evaluates whether the given action exceeds the rate limit.

        Raises:
            HTTPException(429): If the request rate exceeds max_requests within window_seconds.
        """
        if max_requests <= 0:
            return

        now = self._time_provider()
        client_ip = resolve_client_ip(request, settings.TRUSTED_PROXIES)

        # Isolated identity scoping: authenticated user preferred, IP fallback
        if user_id and user_id.strip():
            key = f"{action}:user:{user_id.strip()}"
        else:
            key = f"{action}:ip:{client_ip}"

        cutoff = now - window_seconds

        # Prune entries outside the sliding window
        recent = [ts for ts in self._history[key] if ts > cutoff]
        self._history[key] = recent

        if len(recent) >= max_requests:
            oldest = recent[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            logger.warning(
                "Rate limit exceeded for %s (key=%s, count=%d/%d, retry_after=%ds)",
                action,
                key,
                len(recent),
                max_requests,
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: maximum {max_requests} requests per {window_seconds} second(s) for {action}.",
                headers={"Retry-After": str(retry_after)},
            )

        self._history[key].append(now)

    def reset(self) -> None:
        """Clears all stored rate limit history."""
        self._history.clear()


# Global singleton instance
rate_limiter = InMemoryRateLimiter()


# FastApi Route Dependencies
async def rate_limit_evidence_upload(
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Enforces per-user rate limiting on evidence uploads.

    Executes after get_current_user_id to ensure unauthenticated requests are rejected
    with 401 without consuming or bypassing upload rate limits.
    """
    rate_limiter.check(
        action="evidence_upload",
        user_id=user_id,
        request=request,
        max_requests=settings.RATE_LIMIT_EVIDENCE_UPLOAD_PER_MINUTE,
        window_seconds=60,
    )


async def rate_limit_dossier_pdf(
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Enforces per-user rate limiting on compute-intensive PDF dossier generation."""
    rate_limiter.check(
        action="dossier_pdf_export",
        user_id=user_id,
        request=request,
        max_requests=settings.RATE_LIMIT_DOSSIER_PDF_PER_MINUTE,
        window_seconds=60,
    )
