"""Per-user LLM provider credentials."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class UserLlmSettings(UUIDPrimaryKeyMixin, Base):
    """The key one account uses for agent runs.

    ``api_key_encrypted`` is a Fernet token — the plaintext key never leaves the
    service process and is never returned by the API.
    """

    __tablename__ = "user_llm_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_llm_settings_user"),
        CheckConstraint("provider IN ('openai', 'anthropic')", name="provider_valid"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # OpenAI-compatible gateways need a custom URL; Anthropic may leave it empty.
    base_url: Mapped[str | None] = mapped_column(String(300))
    model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
