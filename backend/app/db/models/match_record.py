"""Persisted, versioned job match results.

A row is keyed by user + profile version + scorer version + job content hash so
that profile edits, JD updates and scorer changes all invalidate stale results.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.types import JSONType


class MatchRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "match_records"
    __table_args__ = (
        CheckConstraint(
            "job_id IS NOT NULL OR job_lead_id IS NOT NULL",
            name="match_target_required",
        ),
        UniqueConstraint(
            "user_id",
            "job_id",
            "job_lead_id",
            "profile_version",
            "scorer_version",
            "job_content_hash",
            name="uq_match_records_key",
        ),
        Index("ix_match_records_user_created", "user_id", "created_at"),
        Index("ix_match_records_job", "job_id"),
        Index("ix_match_records_job_lead", "job_lead_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    job_lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("job_leads.id", ondelete="CASCADE"))
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    job_content_hash: Mapped[str | None] = mapped_column(String(64))
    scorer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    match_level: Mapped[str] = mapped_column(String(16), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
