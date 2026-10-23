"""Job source and sync-run response contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.db.models.enums import SyncStatus
from app.db.models.job import JobSource
from app.db.models.sync_run import SyncRun


class JobSourceRead(BaseModel):
    id: UUID
    source_type: str
    source_key: str
    enabled: bool
    last_success_at: datetime | None
    last_error: str | None
    last_job_count: int
    created_at: datetime
    updated_at: datetime


class ConnectorHealthRead(BaseModel):
    configured: bool
    ok: bool
    message: str
    checked_at: datetime


class SyncRunRead(BaseModel):
    id: UUID
    source_id: UUID
    status: SyncStatus
    started_at: datetime | None
    ended_at: datetime | None
    fetched_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    failed_count: int
    error_message: str | None
    created_at: datetime


class SyncRequest(BaseModel):
    source_id: UUID


class JobSourceUpdate(BaseModel):
    """Admin-editable fields. Secrets are intentionally not accepted here."""

    enabled: bool | None = None
    config: dict[str, object] | None = None


def source_to_read(source: JobSource) -> JobSourceRead:
    return JobSourceRead(
        id=source.id,
        source_type=source.source_type,
        source_key=source.source_key,
        enabled=source.enabled,
        last_success_at=source.last_success_at,
        last_error=source.last_error,
        last_job_count=source.last_job_count,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def sync_run_to_read(run: SyncRun) -> SyncRunRead:
    return SyncRunRead(
        id=run.id,
        source_id=run.source_id,
        status=run.status,
        started_at=run.started_at,
        ended_at=run.ended_at,
        fetched_count=run.fetched_count,
        created_count=run.created_count,
        updated_count=run.updated_count,
        unchanged_count=run.unchanged_count,
        failed_count=run.failed_count,
        error_message=run.error_message,
        created_at=run.created_at,
    )
