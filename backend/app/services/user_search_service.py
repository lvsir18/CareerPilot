"""Per-user search credentials (Tavily), mirroring the per-user LLM keys."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.models.user_search import UserSearchSettings
from app.services.mailbox_secret import decrypt_secret, encrypt_secret
from app.services.secret_store import SecretStoreError
from app.services.user_llm_service import mask_key

logger = get_logger(__name__)

PROVIDER_TAVILY = "tavily"


class UserSearchSettingsService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def get_row(self, user_id: UUID) -> UserSearchSettings | None:
        return self._session.scalar(
            select(UserSearchSettings).where(UserSearchSettings.user_id == user_id)
        )

    def describe(self, user_id: UUID) -> dict[str, Any]:
        row = self.get_row(user_id)
        masked: str | None = None
        if row is not None:
            try:
                payload = decrypt_secret(self._settings, row.api_key_encrypted)
                key = str(payload.get("api_key") or "")
                masked = mask_key(key) if key else None
            except SecretStoreError:
                masked = None
        return {
            "configured": row is not None and masked is not None,
            "provider": row.provider if row else None,
            "key_set": masked is not None,
            "masked_key": masked,
            "server_default_available": bool(self._settings.tavily_api_key),
            "server_default_admins_only": self._settings.shared_search_key_admins_only,
            "provider_enabled": self._settings.search_provider == PROVIDER_TAVILY,
        }

    def upsert(self, user: User, *, api_key: str | None) -> dict[str, Any]:
        cleaned = (api_key or "").strip()
        row = self.get_row(user.id)
        if row is None and not cleaned:
            raise AppError("API_KEY_REQUIRED", "首次配置必须填写 Tavily API Key", status_code=422)
        if cleaned:
            row = row or UserSearchSettings(
                user_id=user.id, provider=PROVIDER_TAVILY, api_key_encrypted=""
            )
            row.api_key_encrypted = encrypt_secret(self._settings, {"api_key": cleaned})
            row.provider = PROVIDER_TAVILY
        self._session.add(row)
        self._session.commit()
        logger.info("user_search_settings_saved", extra={"user_id": str(user.id)})
        return self.describe(user.id)

    def clear(self, user_id: UUID) -> bool:
        row = self.get_row(user_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        logger.info("user_search_settings_cleared", extra={"user_id": str(user_id)})
        return True

    def resolve(self, user_id: UUID) -> str | None:
        """The account's own Tavily key, or ``None`` (caller decides the fallback)."""
        row = self.get_row(user_id)
        if row is None:
            return None
        try:
            payload = decrypt_secret(self._settings, row.api_key_encrypted)
        except SecretStoreError:
            logger.warning("user_search_key_undecryptable", extra={"user_id": str(user_id)})
            return None
        key = str(payload.get("api_key") or "").strip()
        return key or None


def shares_server_search_key(settings: Settings, user: User | None) -> bool:
    """Whether this account may spend the deployment owner's Tavily key."""
    if not settings.tavily_api_key:
        return False
    if not settings.shared_search_key_admins_only:
        return True
    return bool(user and user.email.strip().lower() in settings.admin_email_set)
