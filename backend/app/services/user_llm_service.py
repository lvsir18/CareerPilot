"""Per-user LLM credentials: store, mask, and resolve.

One shared server key means the host's quota pays for every account on the
network. An account can store its own provider key instead; accounts without
one keep working on the server default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.models.user_llm import UserLlmSettings
from app.services.mailbox_secret import decrypt_secret, encrypt_secret
from app.services.secret_store import SecretStoreError

logger = get_logger(__name__)

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
SUPPORTED_PROVIDERS = (PROVIDER_OPENAI, PROVIDER_ANTHROPIC)

DEFAULT_MODELS = {
    PROVIDER_OPENAI: "gpt-4o-mini",
    PROVIDER_ANTHROPIC: "claude-3-5-sonnet-latest",
}


@dataclass(frozen=True)
class LlmConfig:
    """A resolved, ready-to-use model configuration."""

    provider: str
    api_key: str
    base_url: str | None
    model: str


def mask_key(value: str) -> str:
    """Never return a usable key: keep just enough to recognise which one it is."""
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}…{value[-4:]}"


class UserLlmSettingsService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    # ------------------------------------------------------------- read/write
    def get_row(self, user_id: UUID) -> UserLlmSettings | None:
        return self._session.scalar(
            select(UserLlmSettings).where(UserLlmSettings.user_id == user_id)
        )

    def describe(self, user_id: UUID) -> dict[str, Any]:
        """What the settings page may know: never the key itself."""
        row = self.get_row(user_id)
        if row is None:
            return {
                "configured": False,
                "provider": None,
                "base_url": None,
                "model": None,
                "key_set": False,
                "masked_key": None,
                "server_default_available": self._settings.llm_configured,
            }
        masked: str | None = None
        try:
            payload = decrypt_secret(self._settings, row.api_key_encrypted)
            api_key = str(payload.get("api_key") or "")
            masked = mask_key(api_key) if api_key else None
        except SecretStoreError:
            masked = None
        return {
            "configured": True,
            "provider": row.provider,
            "base_url": row.base_url,
            "model": row.model,
            "key_set": masked is not None,
            "masked_key": masked,
            "server_default_available": self._settings.llm_configured,
        }

    def upsert(
        self,
        user: User,
        *,
        provider: str,
        api_key: str | None,
        base_url: str | None,
        model: str | None,
    ) -> dict[str, Any]:
        if provider not in SUPPORTED_PROVIDERS:
            raise AppError(
                "INVALID_PROVIDER",
                f"不支持的模型提供方：{provider}",
                status_code=422,
            )
        row = self.get_row(user.id)
        cleaned_key = (api_key or "").strip()
        if row is None and not cleaned_key:
            raise AppError("API_KEY_REQUIRED", "首次配置必须填写 API Key", status_code=422)
        if cleaned_key:
            row = row or UserLlmSettings(user_id=user.id, provider=provider, api_key_encrypted="")
            row.api_key_encrypted = encrypt_secret(self._settings, {"api_key": cleaned_key})
        row.provider = provider
        row.base_url = (base_url or "").strip() or None
        row.model = (model or "").strip() or None
        self._session.add(row)
        self._session.commit()
        logger.info(
            "user_llm_settings_saved", extra={"user_id": str(user.id), "provider": provider}
        )
        return self.describe(user.id)

    def clear(self, user_id: UUID) -> bool:
        row = self.get_row(user_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        logger.info("user_llm_settings_cleared", extra={"user_id": str(user_id)})
        return True

    # ---------------------------------------------------------------- resolve
    def resolve(self, user_id: UUID) -> LlmConfig | None:
        """The account's own model, or ``None`` to use the server default."""
        row = self.get_row(user_id)
        if row is None:
            return None
        try:
            payload = decrypt_secret(self._settings, row.api_key_encrypted)
        except SecretStoreError:
            # A rotated MAILBOX_SECRET_KEY must degrade to the server default
            # rather than break the agent entirely.
            logger.warning("user_llm_key_undecryptable", extra={"user_id": str(user_id)})
            return None
        api_key = str(payload.get("api_key") or "").strip()
        if not api_key:
            return None
        model = (row.model or "").strip() or DEFAULT_MODELS.get(
            row.provider, DEFAULT_MODELS[PROVIDER_OPENAI]
        )
        return LlmConfig(
            provider=row.provider,
            api_key=api_key,
            base_url=(row.base_url or "").strip() or None,
            model=model,
        )
