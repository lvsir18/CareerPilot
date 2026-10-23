"""Per-user external recruiting account connection metadata.

Only an opaque secret-manager reference is stored here. Passwords, raw cookies
and access tokens must never be persisted in this table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ExternalAuthMode, ExternalConnectionStatus
from app.db.models.types import JSONType, enum_column


class ExternalAccountConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "external_account_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_external_accounts_user_provider"),
        CheckConstraint(
            "auth_mode IN ('oauth', 'browser_session', 'manual_import')",
            name="auth_mode_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'revoked')",
            name="status_valid",
        ),
        Index("ix_external_accounts_user_status", "user_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    auth_mode: Mapped[ExternalAuthMode] = mapped_column(
        enum_column(ExternalAuthMode, "external_auth_mode", length=24), nullable=False
    )
    status: Mapped[ExternalConnectionStatus] = mapped_column(
        enum_column(ExternalConnectionStatus, "external_connection_status", length=16),
        default=ExternalConnectionStatus.PENDING,
        nullable=False,
    )
    # e.g. vault://careerpilot/provider/connection-id — never a raw token.
    secret_reference: Mapped[str | None] = mapped_column(String(500))
    scopes_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
