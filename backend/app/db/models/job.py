"""Company, job source and normalized job models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus
from app.db.models.types import JSONType, enum_column

if TYPE_CHECKING:
    from app.db.models.sync_run import SyncRun


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))


class JobSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("source_type", "source_key", name="uq_job_sources_type_key"),
    )

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_job_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    jobs: Mapped[list[Job]] = relationship(back_populates="source")
    sync_runs: Mapped[list[SyncRun]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "source_job_id", name="uq_jobs_source_job"),
        CheckConstraint("source_url ~ '^https?://'", name="source_url_http"),
        CheckConstraint("status IN ('open', 'closed', 'unknown')", name="status_valid"),
        CheckConstraint(
            "source_method IN ('api', 'public_page', 'manual_import', 'manual_paste', "
            "'fixture', 'unknown')",
            name="source_method_valid",
        ),
        CheckConstraint(
            "verification_status IN ('verified', 'user_confirmed', 'unverified', 'stale')",
            name="verification_status_valid",
        ),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_job_type", "job_type"),
        Index("ix_jobs_city", "city"),
        Index("ix_jobs_published_at", "published_at"),
        Index("ix_jobs_first_seen_at", "first_seen_at"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_recruitment_program", "recruitment_program"),
        Index("ix_jobs_duplicate_group_key", "duplicate_group_key"),
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_sources.id", ondelete="RESTRICT"), nullable=False
    )
    source_job_id: Mapped[str] = mapped_column(String(200), nullable=False)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    department: Mapped[str | None] = mapped_column(String(200))
    location_text: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    job_type: Mapped[str | None] = mapped_column(String(50))
    recruitment_program: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    requirements_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[JobStatus] = mapped_column(
        enum_column(JobStatus, "job_status", length=16),
        default=JobStatus.UNKNOWN,
        nullable=False,
    )
    source_method: Mapped[JobSourceMethod] = mapped_column(
        enum_column(JobSourceMethod, "job_source_method", length=24),
        default=JobSourceMethod.UNKNOWN,
        server_default=JobSourceMethod.UNKNOWN.value,
        nullable=False,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "job_verification_status", length=24),
        default=VerificationStatus.UNVERIFIED,
        server_default=VerificationStatus.UNVERIFIED.value,
        nullable=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    duplicate_group_key: Mapped[str | None] = mapped_column(String(64))
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    source: Mapped[JobSource] = relationship(back_populates="jobs", lazy="selectin")
    company: Mapped[Company] = relationship(lazy="selectin")
