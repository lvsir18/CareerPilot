"""Application tracking and progress-event contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.db.models.application import Application, ApplicationEvent
from app.db.models.enums import (
    ApplicationSourceType,
    ApplicationStatus,
    EventVerificationStatus,
)
from app.schemas.jobs import JobListItem, job_to_list_item
from app.schemas.leads import JobLeadRead, lead_to_read

ACTIVE_STATUSES = {
    ApplicationStatus.PLANNED,
    ApplicationStatus.TO_APPLY,
    ApplicationStatus.PREPARING,
    ApplicationStatus.APPLIED,
    ApplicationStatus.SCREENING,
    ApplicationStatus.ASSESSMENT,
    ApplicationStatus.ONLINE_ASSESSMENT,
    ApplicationStatus.INTERVIEW,
}
STALE_AFTER_DAYS = 14


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ApplicationCreate(BaseModel):
    # Exactly one target family is required: verified Job, JobLead, or an
    # external official URL with snapshots.
    job_id: UUID | None = None
    job_lead_id: UUID | None = None
    external_company: str | None = Field(default=None, max_length=200)
    external_title: str | None = Field(default=None, max_length=300)
    external_url: HttpUrl | None = None
    status: ApplicationStatus = ApplicationStatus.TO_APPLY
    notes: str | None = Field(default=None, max_length=2000)
    applied_at: datetime | None = None

    @field_validator("applied_at")
    @classmethod
    def _applied_at_utc(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value)

    @model_validator(mode="after")
    def _target_required(self) -> Self:
        if not any((self.job_id, self.job_lead_id, self.external_url)):
            raise ValueError("必须提供 job_id、job_lead_id 或 external_url")
        if self.external_url and not (self.external_company and self.external_title):
            raise ValueError("仅链接登记时必须提供公司名称和岗位名称")
        return self


class ApplicationUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)
    external_company: str | None = Field(default=None, max_length=200)
    external_title: str | None = Field(default=None, max_length=300)
    external_url: HttpUrl | None = None


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=1000)
    applied_at: datetime | None = None

    @field_validator("applied_at")
    @classmethod
    def _applied_at_utc(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value)


class ApplicationEventCreate(BaseModel):
    status: ApplicationStatus
    event_time: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)
    evidence_summary: str | None = Field(default=None, max_length=2000)
    source_reference: str | None = Field(default=None, max_length=200)
    source_type: ApplicationSourceType = ApplicationSourceType.MANUAL
    verification_status: EventVerificationStatus = EventVerificationStatus.USER_REPORTED

    @field_validator("event_time")
    @classmethod
    def _event_time_utc(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value)

    @model_validator(mode="after")
    def _manual_only(self) -> Self:
        # Email/admin evidence is written by trusted services. Browser-assisted
        # clients are reserved until the optional extension is reviewed/enabled.
        if self.source_type != ApplicationSourceType.MANUAL:
            raise ValueError("当前仅支持用户手动事件；邮件/浏览器证据由专用接口写入")
        if self.verification_status not in {
            EventVerificationStatus.USER_REPORTED,
            EventVerificationStatus.UNVERIFIED,
        }:
            raise ValueError("手动事件只能标记为用户填报或未核验")
        return self


class ApplicationEventRead(BaseModel):
    id: UUID
    application_id: UUID
    previous_status: ApplicationStatus | None
    new_status: ApplicationStatus
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    event_time: datetime
    created_at: datetime
    actor: str
    evidence_type: str
    source_type: str
    source_reference: str | None
    evidence_summary: str | None
    verification_status: str
    note: str | None


class ApplicationRead(BaseModel):
    id: UUID
    status: ApplicationStatus
    applied_at: datetime | None
    last_confirmed_at: datetime | None
    needs_review: bool
    stale_days: int | None
    notes: str | None
    source_of_truth: str
    source_type: str
    source_reference: str | None
    external_company: str | None
    external_title: str | None
    external_url: str | None
    created_at: datetime
    updated_at: datetime
    job: JobListItem | None
    lead: JobLeadRead | None
    latest_event: ApplicationEventRead | None


class ApplicationDetail(ApplicationRead):
    events: list[ApplicationEventRead]


def event_to_read(event: ApplicationEvent) -> ApplicationEventRead:
    return ApplicationEventRead(
        id=event.id,
        application_id=event.application_id,
        previous_status=event.from_status,
        new_status=event.to_status,
        from_status=event.from_status,
        to_status=event.to_status,
        event_time=event.event_time,
        created_at=event.created_at,
        actor=event.actor,
        evidence_type=event.evidence_type,
        source_type=event.source_type,
        source_reference=event.source_reference,
        evidence_summary=event.evidence_summary,
        verification_status=event.verification_status,
        note=event.note,
    )


def application_staleness(row: Application) -> tuple[bool, int | None]:
    if row.status not in ACTIVE_STATUSES:
        return False, None
    marker = row.last_confirmed_at or row.updated_at
    age = datetime.now(UTC) - marker
    days = max(0, age.days)
    return days >= STALE_AFTER_DAYS, days


def application_to_read(row: Application) -> ApplicationRead:
    stale, stale_days = application_staleness(row)
    events = list(row.events)
    latest = events[-1] if events else None
    return ApplicationRead(
        id=row.id,
        status=row.status,
        applied_at=row.applied_at,
        last_confirmed_at=row.last_confirmed_at,
        needs_review=stale,
        stale_days=stale_days,
        notes=row.notes,
        source_of_truth=row.source_of_truth,
        source_type=row.source_type,
        source_reference=row.source_reference,
        external_company=row.external_company,
        external_title=row.external_title,
        external_url=row.external_url,
        created_at=row.created_at,
        updated_at=row.updated_at,
        job=job_to_list_item(row.job) if row.job else None,
        lead=lead_to_read(row.lead) if row.lead else None,
        latest_event=event_to_read(latest) if latest else None,
    )
