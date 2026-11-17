"""Mailbox connections, sync cursors/runs and recruitment email candidates.

Credentials are stored only as an opaque encrypted blob (Fernet). No plaintext
authorization code or refresh token is persisted.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MailboxConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mailbox_connections"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "email_address", name="uq_mailbox_user_provider_email"
        ),
        CheckConstraint("provider IN ('qq_imap', 'gmail')", name="mailbox_provider_valid"),
        CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'revoked', 'error')",
            name="mailbox_status_valid",
        ),
        Index("ix_mailbox_user_status", "user_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # Fernet-encrypted JSON payload; never plaintext.
    encrypted_secret: Mapped[str | None] = mapped_column(Text)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))


class MailboxSyncCursor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mailbox_sync_cursors"
    __table_args__ = (UniqueConstraint("connection_id", "folder", name="uq_mailbox_cursor_folder"),)

    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("mailbox_connections.id", ondelete="CASCADE"), nullable=False
    )
    folder: Mapped[str] = mapped_column(String(100), nullable=False, default="INBOX")
    gmail_history_id: Mapped[str | None] = mapped_column(String(64))
    imap_uidvalidity: Mapped[int | None] = mapped_column(Integer)
    imap_last_uid: Mapped[int | None] = mapped_column(Integer)


class MailboxSyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mailbox_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="mailbox_sync_status_valid",
        ),
        Index("ix_mailbox_sync_runs_connection", "connection_id", "created_at"),
    )

    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("mailbox_connections.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(String(1000))


class RecruitmentEventCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recruitment_event_candidates"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "message_reference", name="uq_recruitment_candidate_message"
        ),
        CheckConstraint(
            "review_status IN ('pending', 'conflict', 'confirmed', 'discarded')",
            name="candidate_review_status_valid",
        ),
        CheckConstraint(
            "conflict_kind IN ('none', 'duplicate', 'out_of_order', 'ambiguous_match', "
            "'status_conflict', 'missing_information')",
            name="candidate_conflict_kind_valid",
        ),
        Index("ix_recruitment_candidates_user_status", "user_id", "review_status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("mailbox_connections.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    message_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    matched_application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    parsed_company: Mapped[str | None] = mapped_column(String(200))
    parsed_title: Mapped[str | None] = mapped_column(String(300))
    parsed_status: Mapped[str | None] = mapped_column(String(32))
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    conflict_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    conflict_reason: Mapped[str | None] = mapped_column(String(500))
