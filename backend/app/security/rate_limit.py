"""Redis-backed login/registration rate limiting.

Two dimensions are enforced: client IP and account (email hash). Keys store no
plaintext email. Redis failures **fail open** with a warning: authentication must
remain available when the cache is down, and the outage is visible in logs.
"""

from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError
from starlette.requests import Request

from app.core.cache import get_redis
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None
    degraded: bool = False


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


def get_client_ip(request: Request, settings: Settings) -> str | None:
    """Client IP.

    ``X-Forwarded-For`` is only honoured when explicitly enabled, otherwise a
    client could spoof the header and bypass IP throttling.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    return request.client.host if request.client else None


class LoginRateLimiter:
    def __init__(
        self,
        redis_client: Redis,
        *,
        enabled: bool,
        ip_attempts: int,
        ip_window_seconds: int,
        account_attempts: int,
        account_window_seconds: int,
        key_prefix: str = "cp:rl",
    ) -> None:
        self._redis = redis_client
        self._enabled = enabled
        self._ip_attempts = ip_attempts
        self._ip_window = ip_window_seconds
        self._account_attempts = account_attempts
        self._account_window = account_window_seconds
        self._prefix = key_prefix

    def _key(self, scope: str, dimension: str, identifier: str) -> str:
        return f"{self._prefix}:{scope}:{dimension}:{identifier}"

    def _consume(self, key: str, window_seconds: int) -> int:
        pipeline = self._redis.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, window_seconds)
        count, _ = pipeline.execute()
        return int(count)

    def consume(
        self,
        scope: str,
        *,
        ip: str | None,
        email: str | None,
    ) -> RateLimitDecision:
        if not self._enabled:
            return RateLimitDecision(allowed=True)

        try:
            counts: list[tuple[int, int]] = []
            if ip:
                key = self._key(scope, "ip", hash_identifier(ip))
                counts.append((self._consume(key, self._ip_window), self._ip_attempts))
            if email:
                key = self._key(scope, "account", hash_identifier(email))
                counts.append((self._consume(key, self._account_window), self._account_attempts))
        except RedisError as exc:
            logger.warning(
                "rate_limit_degraded",
                extra={"scope": scope, "error_type": type(exc).__name__},
            )
            return RateLimitDecision(allowed=True, degraded=True)
        except Exception as exc:  # defensive: never break auth on limiter bugs
            logger.warning(
                "rate_limit_degraded",
                extra={"scope": scope, "error_type": type(exc).__name__},
            )
            return RateLimitDecision(allowed=True, degraded=True)

        exceeded = [(count, limit) for count, limit in counts if count > limit]
        if exceeded:
            retry_after = max(
                self._ip_window if ip else 0,
                self._account_window if email else 0,
            )
            logger.warning(
                "rate_limit_exceeded",
                extra={"scope": scope, "ip_hash": hash_identifier(ip) if ip else None},
            )
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
        return RateLimitDecision(allowed=True)

    def reset_account(self, scope: str, email: str) -> None:
        """Clear the account counter after a successful authentication."""
        try:
            self._redis.delete(self._key(scope, "account", hash_identifier(email)))
        except Exception:
            # Reset is best-effort; the IP counter still applies.
            return


@lru_cache
def get_login_rate_limiter() -> LoginRateLimiter:
    settings = get_settings()
    return LoginRateLimiter(
        get_redis(),
        enabled=settings.login_rate_limit_enabled,
        ip_attempts=settings.login_rate_limit_ip_attempts,
        ip_window_seconds=settings.login_rate_limit_ip_window_seconds,
        account_attempts=settings.login_rate_limit_account_attempts,
        account_window_seconds=settings.login_rate_limit_account_window_seconds,
    )
