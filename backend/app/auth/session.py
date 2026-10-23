"""Opaque session tokens stored as SHA-256 hashes in PostgreSQL.

Cookies carry the raw token; only its hash is persisted, so a database leak does
not expose usable sessions. Logout revokes the row immediately.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Response

from app.core.config import Settings

SESSION_COOKIE_PATH = "/"


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.auth_session_ttl_days)


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.effective_cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.effective_cookie_domain,
        path=SESSION_COOKIE_PATH,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=SESSION_COOKIE_PATH,
        domain=settings.effective_cookie_domain,
        httponly=True,
        secure=settings.effective_cookie_secure,
        samesite=settings.cookie_samesite,
    )
