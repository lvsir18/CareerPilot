"""Audit record for one data-source synchronization attempt."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.enums import SyncStatus
from app.db.models.types import enum_column

if TYPE_CHECKING:
    from app.db.models.job import JobSource


class SyncRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'success', 'partial', 'failed')",
            name="status_valid",
        ),
        Index("ix_sync_runs_source_created", "source_id", "created_at"),
        Index("ix_sync_runs_status", "status"),
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_sources.id", ondelete="CASCADE"), nullable=False
    )
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[SyncStatus] = mapped_column(
        enum_column(SyncStatus, "sync_status", length=16),
        default=SyncStatus.QUEUED,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped[JobSource] = relationship(lazy="selectin")
