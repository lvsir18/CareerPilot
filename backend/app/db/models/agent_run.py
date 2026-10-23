"""Durable Agent run + event log.

The run row is the source of truth for execution state; events are append-only
and drive SSE replay, so a disconnected browser never loses the result.
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
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.types import JSONType

RUN_STATUSES = (
    "queued",
    "running",
    "waiting_for_user",
    "completed",
    "partial",
    "failed",
    "cancelled",
    "timed_out",
)


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_agent_runs_user_request"),
        CheckConstraint(
            "status IN ('queued', 'running', 'waiting_for_user', 'completed', "
            "'partial', 'failed', 'cancelled', 'timed_out')",
            name="agent_run_status_valid",
        ),
        Index("ix_agent_runs_user_created", "user_id", "created_at"),
        Index("ix_agent_runs_thread", "thread_id", "created_at"),
        Index("ix_agent_runs_status_created", "status", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_threads.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AgentRunEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_seq"),
        Index("ix_agent_run_events_run_seq", "run_id", "sequence"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    safe_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Optional human-readable note; payloads stay structured and safe.
    note: Mapped[str | None] = mapped_column(Text)
