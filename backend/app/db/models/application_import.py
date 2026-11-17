"""Preview/confirmation records for user-uploaded recruitment emails."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ApplicationStatus
from app.db.models.types import JSONType, enum_column


class ApplicationImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_imports"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_application_imports_user_hash"),
        CheckConstraint(
            "status IN ('ready', 'needs_review', 'confirmed', 'discarded')",
            name="status_valid",
        ),
        Index("ix_application_imports_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="needs_review", nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500))
    sender: Mapped[str | None] = mapped_column(String(500))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parsed_company: Mapped[str | None] = mapped_column(String(200))
    parsed_title: Mapped[str | None] = mapped_column(String(300))
    parsed_status: Mapped[ApplicationStatus | None] = mapped_column(
        enum_column(ApplicationStatus, "application_import_parsed_status", length=32)
    )
    parsed_event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    matched_application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    confirmed_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("application_events.id", ondelete="SET NULL")
    )
    body_excerpt: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
