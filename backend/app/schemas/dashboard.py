"""Dashboard aggregate contracts."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DashboardCounts(BaseModel):
    saved: int = 0
    planned: int = 0
    applied: int = 0
    screening: int = 0
    assessment: int = 0
    interview: int = 0
    offer: int = 0
    needs_review: int = 0


class DashboardJob(BaseModel):
    id: UUID
    company: str
    title: str
    city: str | None
    job_type: str | None
    source_url: str
    verification_status: str
    published_at: datetime | None
    first_seen_at: datetime


class DashboardEvent(BaseModel):
    id: UUID
    application_id: UUID
    company: str
    title: str
    status: str
    event_time: datetime | None
    source_type: str
    evidence_type: str
    verification_status: str
    summary: str | None


class DashboardUpcoming(BaseModel):
    application_id: UUID
    company: str
    title: str
    status: str
    starts_at: datetime
    source_type: str
    verification_status: str


class DashboardCalendarEvent(BaseModel):
    """Only explicit appointment events belong on the interview calendar."""

    id: UUID
    application_id: UUID
    company: str
    title: str
    status: str
    starts_at: datetime
    source_type: str
    verification_status: str


class DashboardCalendar(BaseModel):
    events: list[DashboardCalendarEvent] = Field(default_factory=list)
    range_start: datetime
    range_end: datetime
    generated_at: datetime


class DashboardSummary(BaseModel):
    counts: DashboardCounts
    latest_jobs: list[DashboardJob] = Field(default_factory=list)
    recent_events: list[DashboardEvent] = Field(default_factory=list)
    upcoming_events: list[DashboardUpcoming] = Field(default_factory=list)
    generated_at: datetime
    date: date
