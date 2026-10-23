"""Reusable authentication dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.service import AuthService
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models.user import User
from app.db.session import get_db


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    user = AuthService(session, settings).resolve_session(token)
    if user is None:
        raise AppError(
            code="AUTH_REQUIRED",
            message="登录已失效，请重新登录",
            status_code=401,
        )
    # Correlation for logs only; authorization always uses the DB row above.
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def require_admin(user: CurrentUser, settings: AppSettings) -> User:
    """Admin access is granted by configured email list (no self-service role)."""
    if user.email.strip().lower() not in settings.admin_email_set:
        raise AppError(
            code="ADMIN_REQUIRED",
            message="需要管理员权限",
            status_code=403,
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]
