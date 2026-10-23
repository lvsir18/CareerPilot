"""CSRF protection for cookie-based sessions.

Two independent checks protect state-changing requests:

1. **Trusted Origin**: ``Origin`` (or ``Referer`` as fallback) must match the
   configured frontend/API origins. This alone also protects pre-auth actions
   such as login and registration (login CSRF).
2. **Double-submit token**: once a session cookie exists, the request must echo
   the non-HttpOnly ``careerpilot_csrf`` cookie in ``X-CSRF-Token``. The token is
   rotated on every login/registration.

SameSite=Lax and CORS are defence-in-depth, not the primary control.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import Depends, Request, Response

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

logger = get_logger(__name__)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _origin_of(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _cookie_kwargs(settings: Settings) -> dict[str, object]:
    return {
        "secure": settings.effective_cookie_secure,
        "samesite": settings.cookie_samesite,
        "domain": settings.effective_cookie_domain,
        "path": "/",
    }


def set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_days * 24 * 60 * 60,
        httponly=False,  # the browser client must echo it in a header
        **_cookie_kwargs(settings),
    )


def clear_csrf_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        domain=settings.effective_cookie_domain,
        secure=settings.effective_cookie_secure,
        httponly=False,
        samesite=settings.cookie_samesite,
    )


def issue_csrf_token(response: Response, settings: Settings) -> str:
    token = generate_csrf_token()
    set_csrf_cookie(response, token, settings)
    return token


def verify_trusted_origin(request: Request, settings: Settings) -> None:
    if request.method in SAFE_METHODS:
        return

    origin = _origin_of(request.headers.get("origin"))
    if origin is None:
        origin = _origin_of(request.headers.get("referer"))

    if origin is None:
        raise AppError(
            code="CSRF_ORIGIN_MISSING",
            message="请求缺少可信来源信息，已拒绝",
            status_code=403,
        )
    if origin not in settings.effective_csrf_origins:
        logger.warning("csrf_origin_rejected", extra={"origin": origin})
        raise AppError(
            code="CSRF_ORIGIN_INVALID",
            message="请求来源不受信任，已拒绝",
            status_code=403,
        )


def verify_origin_dependency(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Origin-only check used for login/registration (no session yet)."""
    verify_trusted_origin(request, settings)


def require_csrf(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Origin + double-submit token for authenticated state-changing requests."""
    if request.method in SAFE_METHODS:
        return

    verify_trusted_origin(request, settings)

    if not request.cookies.get(settings.session_cookie_name):
        # No session: login/register handled separately; nothing else should be
        # treatable as authenticated. Authentication itself will return 401.
        return

    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
    ):
        logger.warning("csrf_token_rejected", extra={"path": request.url.path})
        raise AppError(
            code="CSRF_TOKEN_INVALID",
            message="CSRF 校验失败，请刷新页面后重试",
            status_code=403,
        )
