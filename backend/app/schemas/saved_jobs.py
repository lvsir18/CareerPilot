"""Saved job contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models.enums import SavedListType
from app.db.models.saved_job import SavedJob
from app.schemas.jobs import JobListItem, job_to_list_item


class SaveJobRequest(BaseModel):
    list_type: SavedListType = SavedListType.SAVED
    note: str | None = Field(default=None, max_length=1000)


class SavedJobRead(BaseModel):
    id: UUID
    list_type: SavedListType
    note: str | None
    created_at: datetime
    job: JobListItem


def saved_job_to_read(row: SavedJob) -> SavedJobRead:
    return SavedJobRead(
        id=row.id,
        list_type=row.list_type,
        note=row.note,
        created_at=row.created_at,
        job=job_to_list_item(row.job),
    )
