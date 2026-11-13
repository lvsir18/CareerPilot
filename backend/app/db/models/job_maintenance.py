"""User-triggered job library maintenance runs (refresh / discover / prune)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.types import JSONType


class JobMaintenanceRun(UUIDPrimaryKeyMixin, Base):
    """One batch operation the user started from the job library.

    Persisted so the UI can restore progress after a reload and so the worker
    has an idempotency key: the same ``dedupe_key`` while queued/running returns
    the existing run instead of starting a second crawl.
    """

    __tablename__ = "job_maintenance_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('refresh', 'discover', 'prune')", name="kind_valid"),
        CheckConstraint(
            "status IN ('queued', 'running', 'success', 'partial', 'failed', 'cancelled')",
            name="status_valid",
        ),
        Index("ix_job_maintenance_runs_user_created", "user_id", "created_at"),
        Index("ix_job_maintenance_runs_status", "status"),
        Index("ix_job_maintenance_runs_dedupe", "dedupe_key", "status"),
    )

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # Hash of kind + scope + options; a repeat click must not start a second run.
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    # {total, processed, counters: {...}, current: "公司 · 岗位"}
    progress_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    # {items: [...], summary: {...}, unsupported: [...]}
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
