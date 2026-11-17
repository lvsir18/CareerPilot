"""Redis client factory used for readiness checks and Celery broker access."""

from __future__ import annotations

from redis import Redis

from app.core.config import get_settings

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_connect_timeout_seconds,
            decode_responses=True,
        )
    return _redis_client


def check_redis() -> bool:
    """Return True when the broker answers PING, False otherwise."""
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
    _redis_client = None
