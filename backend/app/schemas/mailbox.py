"""Mailbox connection and recruitment candidate contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class MailboxRead(BaseModel):
    id: UUID
    provider: str
    email_address: str
    status: str
    sync_enabled: bool
    last_sync_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    created_at: datetime


class QQConnectRequest(BaseModel):
    email_address: EmailStr
    auth_code: str = Field(min_length=4, max_length=200)


class MailboxUpdate(BaseModel):
    sync_enabled: bool | None = None


class MailboxSyncRunRead(BaseModel):
    id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    scanned_count: int
    candidate_count: int
    duplicate_count: int
    error_count: int
    error_summary: str | None


class RecruitmentCandidateRead(BaseModel):
    id: UUID
    provider: str
    matched_application_id: UUID | None
    parsed_company: str | None
    parsed_title: str | None
    parsed_status: str | None
    event_time: datetime | None
    scheduled_event_time: datetime | None
    confidence: float
    evidence_summary: str | None
    review_status: str
    conflict_kind: str
    conflict_reason: str | None
    created_at: datetime


class CandidateConfirmRequest(BaseModel):
    application_id: UUID | None = None
    status: str | None = None
    event_time: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)
    keep_current: bool = False


class GmailAuthorizeRead(BaseModel):
    configured: bool
    authorize_url: str | None
    message: str


def mailbox_to_read(row) -> MailboxRead:
    return MailboxRead(
        id=row.id,
        provider=row.provider,
        email_address=row.email_address,
        status=row.status,
        sync_enabled=row.sync_enabled,
        last_sync_at=row.last_sync_at,
        last_success_at=row.last_success_at,
        last_error=row.last_error,
        created_at=row.created_at,
    )


def candidate_to_read(row) -> RecruitmentCandidateRead:
    return RecruitmentCandidateRead(
        id=row.id,
        provider=row.provider,
        matched_application_id=row.matched_application_id,
        parsed_company=row.parsed_company,
        parsed_title=row.parsed_title,
        parsed_status=row.parsed_status,
        event_time=row.event_time,
        scheduled_event_time=row.scheduled_event_time,
        confidence=row.confidence,
        evidence_summary=row.evidence_summary,
        review_status=row.review_status,
        conflict_kind=row.conflict_kind,
        conflict_reason=row.conflict_reason,
        created_at=row.created_at,
    )
