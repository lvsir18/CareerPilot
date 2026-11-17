"""External account connection lifecycle.

Security rules:
- Never accepts or returns passwords/cookies/raw tokens.
- Only opaque ``vault://`` or ``secret://`` references are stored.
- OAuth/browser-session providers must be explicitly allow-listed in config.
- Every lookup is scoped by ``user_id``; cross-user access returns 404.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.enums import ExternalAuthMode, ExternalConnectionStatus
from app.db.models.external_account import ExternalAccountConnection

_PROVIDER = re.compile(r"^[a-z0-9][a-z0-9_-]{1,49}$")
_SECRET_REFERENCE = re.compile(r"^(vault|secret)://[A-Za-z0-9_.:/@-]{3,480}$")


class ExternalAccountService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def _allowed_providers(self) -> set[str]:
        return {item.strip().lower() for item in self._settings.external_auth_allowed_providers}

    def _check_mode_allowed(self, provider: str, auth_mode: ExternalAuthMode) -> None:
        if auth_mode == ExternalAuthMode.MANUAL_IMPORT:
            return
        if provider not in self._allowed_providers():
            raise AppError(
                code="EXTERNAL_PROVIDER_NOT_AUTHORIZED",
                message="该招聘平台尚未获得接入许可",
                status_code=403,
            )
        if (
            auth_mode == ExternalAuthMode.BROWSER_SESSION
            and not self._settings.external_auth_allow_browser_session
        ):
            raise AppError(
                code="BROWSER_SESSION_NOT_ENABLED",
                message="平台未启用交互式浏览器会话连接",
                status_code=403,
            )

    def _validate_secret_reference(self, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SECRET_REFERENCE.fullmatch(value):
            raise AppError(
                code="SECRET_REFERENCE_INVALID",
                message="只允许保存密钥管理系统的引用，不允许明文密码或 Token",
                status_code=422,
            )
        return value

    def _normalize_expiry(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    def _expire_if_needed(self, connection: ExternalAccountConnection, now: datetime) -> bool:
        if (
            connection.status == ExternalConnectionStatus.ACTIVE
            and connection.expires_at is not None
            and connection.expires_at <= now
        ):
            connection.status = ExternalConnectionStatus.EXPIRED
            connection.secret_reference = None
            return True
        return False

    def create_or_update(
        self,
        user_id: UUID,
        *,
        provider: str,
        auth_mode: ExternalAuthMode,
        secret_reference: str | None,
        scopes: list[str],
        expires_at: datetime | None,
    ) -> ExternalAccountConnection:
        provider = provider.strip().lower()
        if not _PROVIDER.fullmatch(provider):
            raise AppError(
                code="INVALID_PROVIDER",
                message="招聘平台标识不合法",
                status_code=422,
            )
        self._check_mode_allowed(provider, auth_mode)

        reference = self._validate_secret_reference(secret_reference)
        if auth_mode != ExternalAuthMode.MANUAL_IMPORT and not reference:
            raise AppError(
                code="SECRET_REFERENCE_REQUIRED",
                message="授权连接必须提供密钥引用",
                status_code=422,
            )

        expiry = self._normalize_expiry(expires_at)
        now = datetime.now(UTC)
        if expiry is not None and expiry <= now:
            raise AppError(
                code="CONNECTION_ALREADY_EXPIRED",
                message="过期时间必须晚于当前时间",
                status_code=422,
            )

        connection = self._session.scalar(
            select(ExternalAccountConnection).where(
                ExternalAccountConnection.user_id == user_id,
                ExternalAccountConnection.provider == provider,
            )
        )
        if connection is None:
            connection = ExternalAccountConnection(user_id=user_id, provider=provider)
            self._session.add(connection)

        connection.auth_mode = auth_mode
        connection.secret_reference = reference
        connection.scopes_json = list(
            dict.fromkeys(scope.strip() for scope in scopes if scope.strip())
        )
        connection.expires_at = expiry
        connection.status = ExternalConnectionStatus.ACTIVE
        connection.revoked_at = None
        connection.last_verified_at = now
        self._session.commit()
        self._session.refresh(connection)
        return connection

    def list_for_user(self, user_id: UUID) -> list[ExternalAccountConnection]:
        now = datetime.now(UTC)
        connections = list(
            self._session.scalars(
                select(ExternalAccountConnection)
                .where(ExternalAccountConnection.user_id == user_id)
                .order_by(ExternalAccountConnection.created_at)
            )
        )
        changed = False
        for connection in connections:
            changed = self._expire_if_needed(connection, now) or changed
        if changed:
            self._session.commit()
        return connections

    def get_for_user(self, user_id: UUID, connection_id: UUID) -> ExternalAccountConnection:
        connection = self._session.scalar(
            select(ExternalAccountConnection).where(
                ExternalAccountConnection.user_id == user_id,
                ExternalAccountConnection.id == connection_id,
            )
        )
        if connection is None:
            raise AppError(
                code="EXTERNAL_ACCOUNT_NOT_FOUND",
                message="外部账号连接不存在",
                status_code=404,
            )
        if self._expire_if_needed(connection, datetime.now(UTC)):
            self._session.commit()
        return connection

    def revoke(self, user_id: UUID, connection_id: UUID) -> ExternalAccountConnection:
        connection = self.get_for_user(user_id, connection_id)
        connection.status = ExternalConnectionStatus.REVOKED
        connection.revoked_at = datetime.now(UTC)
        connection.secret_reference = None
        self._session.commit()
        self._session.refresh(connection)
        return connection

    def active_for_user(self, user_id: UUID, provider: str) -> ExternalAccountConnection | None:
        connection = self._session.scalar(
            select(ExternalAccountConnection).where(
                ExternalAccountConnection.user_id == user_id,
                ExternalAccountConnection.provider == provider.strip().lower(),
            )
        )
        if connection is None:
            return None
        if self._expire_if_needed(connection, datetime.now(UTC)):
            self._session.commit()
        return connection if connection.status == ExternalConnectionStatus.ACTIVE else None
