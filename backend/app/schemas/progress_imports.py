"""Email/browser progress import contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.db.models.enums import ApplicationStatus


class ApplicationImportRead(BaseModel):
    id: UUID
    status: str
    filename: str
    subject: str | None
    sender: str | None
    received_at: datetime | None
    parsed_company: str | None
    parsed_title: str | None
    parsed_status: ApplicationStatus | None
    parsed_event_time: datetime | None
    confidence: float
    matched_application_id: UUID | None
    confirmed_event_id: UUID | None
    body_excerpt: str | None
    warnings: list[str]
    duplicate: bool = False
    requires_confirmation: bool = True
    confirmed_at: datetime | None
    created_at: datetime


class ApplicationImportConfirm(BaseModel):
    application_id: UUID | None = None
    status: ApplicationStatus | None = None
    event_time: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("event_time")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
