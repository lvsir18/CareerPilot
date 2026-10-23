"""Candidate job leads and source evidence.

A lead is intentionally separate from a verified ``Job``: a search result or a
user pasted JD must not be presented as a complete official job.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import JobSourceMethod, LeadVerificationStatus
from app.db.models.types import enum_column

if TYPE_CHECKING:
    from app.db.models.job import Company, Job


class JobLead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_leads"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_job_leads_dedupe_key"),
        CheckConstraint(
            "verification_status IN ('search_snippet_only', 'user_provided', "
            "'verified_official', 'stale')",
            name="verification_status_valid",
        ),
        CheckConstraint(
            "source_method IN ('search_discovery', 'manual_import', 'public_page', 'manual_paste')",
            name="source_method_valid",
        ),
        Index("ix_job_leads_owner_status", "owner_user_id", "verification_status"),
        Index("ix_job_leads_company", "company_id"),
        Index("ix_job_leads_last_seen", "last_seen_at"),
    )

    # NULL = public discovery result; set = private user import.
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    official_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    source_method: Mapped[JobSourceMethod] = mapped_column(
        enum_column(JobSourceMethod, "job_lead_source_method", length=24),
        nullable=False,
    )
    verification_status: Mapped[LeadVerificationStatus] = mapped_column(
        enum_column(LeadVerificationStatus, "job_lead_verification_status", length=32),
        default=LeadVerificationStatus.SEARCH_SNIPPET_ONLY,
        nullable=False,
    )
    published_date: Mapped[date | None] = mapped_column(Date)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verification_error: Mapped[str | None] = mapped_column(String(500))
    last_verification_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    source_payload_hash: Mapped[str | None] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)

    company: Mapped[Company] = relationship(lazy="selectin")
    job: Mapped[Job | None] = relationship(lazy="selectin")


class SourceEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "source_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_kind IN ('search_result', 'official_page', 'user_paste', "
            "'verification_attempt')",
            name="evidence_kind_valid",
        ),
        CheckConstraint(
            "verification_method IN ('search_provider', 'official_list_page', "
            "'public_page_parse', 'user_confirmed', 'none')",
            name="verification_method_valid",
        ),
        CheckConstraint(
            "job_id IS NOT NULL OR lead_id IS NOT NULL",
            name="job_or_lead_required",
        ),
        Index("ix_source_evidence_job", "job_id"),
        Index("ix_source_evidence_lead", "lead_id"),
    )

    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("job_leads.id", ondelete="CASCADE"))
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(500))
    verification_method: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
