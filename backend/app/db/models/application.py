"""Manually tracked job applications and their status history."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ApplicationStatus
from app.db.models.types import enum_column

if TYPE_CHECKING:
    from app.db.models.job import Job
    from app.db.models.job_lead import JobLead
    from app.db.models.user import User

_STATUS_SQL = (
    "'saved', 'planned', 'to_apply', 'preparing', 'applied', 'screening', "
    "'assessment', 'online_assessment', 'interview', 'offer', 'rejected', "
    "'withdrawn', 'closed', 'unknown'"
)
_SOURCE_SQL = "'manual', 'email_import', 'official_api', 'browser_assisted'"
_VERIFICATION_SQL = (
    "'user_reported', 'email_confirmed', 'website_user_confirmed', 'official_api', 'unverified'"
)


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_applications_user_dedupe"),
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="status_valid"),
        CheckConstraint(f"source_type IN ({_SOURCE_SQL})", name="source_type_valid"),
        CheckConstraint(
            "job_id IS NOT NULL OR job_lead_id IS NOT NULL OR external_url IS NOT NULL",
            name="application_target_required",
        ),
        CheckConstraint(
            "external_url IS NULL OR external_url ~ '^https?://'",
            name="external_url_http",
        ),
        Index("ix_applications_user_created", "user_id", "created_at"),
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    job_lead_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_leads.id", ondelete="SET NULL")
    )
    external_company: Mapped[str | None] = mapped_column(String(200))
    external_title: Mapped[str | None] = mapped_column(String(300))
    external_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[ApplicationStatus] = mapped_column(
        enum_column(ApplicationStatus, "application_status", length=32),
        default=ApplicationStatus.TO_APPLY,
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_of_truth: Mapped[str] = mapped_column(String(32), default="user_manual", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(200))
    dedupe_key: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="applications")
    job: Mapped[Job | None] = relationship(lazy="selectin")
    lead: Mapped[JobLead | None] = relationship(lazy="selectin")
    events: Mapped[list[ApplicationEvent]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ApplicationEvent.event_time",
    )


class ApplicationEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "application_events"
    __table_args__ = (
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUS_SQL})",
            name="from_status_valid",
        ),
        CheckConstraint(f"to_status IN ({_STATUS_SQL})", name="to_status_valid"),
        CheckConstraint(f"source_type IN ({_SOURCE_SQL})", name="source_type_valid"),
        CheckConstraint(
            f"verification_status IN ({_VERIFICATION_SQL})",
            name="verification_status_valid",
        ),
        Index("ix_application_events_application_created", "application_id", "created_at"),
        Index("ix_application_events_application_time", "application_id", "event_time"),
        Index(
            "uq_application_events_source_ref",
            "application_id",
            "source_type",
            "source_reference",
            unique=True,
            postgresql_where=text("source_reference IS NOT NULL"),
        ),
    )

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        enum_column(ApplicationStatus, "application_event_from_status", length=32)
    )
    to_status: Mapped[ApplicationStatus] = mapped_column(
        enum_column(ApplicationStatus, "application_event_to_status", length=32),
        nullable=False,
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # ``event_time`` defaults to "when the status was recorded"; only explicit
    # appointments (assessment/interview with a user-supplied time) are calendar
    # entries. Keeping the flag on the row avoids guessing from timestamps.
    is_scheduled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    # A rescheduled/cancelled appointment keeps its row for audit but stops being
    # an active calendar slot; superseding is never a delete.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    # Kept for M1 compatibility; new code uses source_type.
    evidence_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(200))
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(
        String(32), default="user_reported", nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    application: Mapped[Application] = relationship(back_populates="events")
