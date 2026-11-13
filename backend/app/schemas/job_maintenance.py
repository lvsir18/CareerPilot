"""Contracts for user-triggered job library maintenance."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MaintenanceKind = Literal["refresh", "discover", "prune"]


class MaintenanceScope(BaseModel):
    """The filter the user is looking at, sent verbatim from the job library URL."""

    q: str | None = Field(default=None, max_length=200)
    companies: list[str] = Field(default_factory=list, max_length=20)
    cities: list[str] = Field(default_factory=list, max_length=20)
    job_types: list[str] = Field(default_factory=list, max_length=10)
    source_types: list[str] = Field(default_factory=list, max_length=10)
    recruitment_programs: list[str] = Field(default_factory=list, max_length=20)


class MaintenanceCreate(BaseModel):
    kind: MaintenanceKind = "refresh"
    scope: MaintenanceScope = Field(default_factory=MaintenanceScope)
    # "复核已有岗位" defaults on; "发现新增岗位" is opt-in.
    recheck: bool = True
    discover: bool = False
    # A sweep may cover a large slice; the cooldown below keeps repeat clicks
    # moving forward instead of re-crawling the same postings.
    max_jobs: int | None = Field(default=None, ge=1, le=200)
    # Skip postings verified within N hours (0 = no cooldown, max 7 days).
    cooldown_hours: int | None = Field(default=None, ge=0, le=168)


class MaintenanceRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    progress: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class MaintenanceAccepted(BaseModel):
    run_id: UUID
    status: str
    # True when an identical run was already queued/running (repeat click).
    reused: bool


class PrunePreviewItem(BaseModel):
    job_id: str
    company: str | None = None
    title: str | None = None
    city: str | None = None
    closed_checked_at: str | None = None
    closed_evidence: str | None = None


class PrunePreview(BaseModel):
    count: int
    items: list[PrunePreviewItem]
    truncated: bool = False


def maintenance_to_read(run: Any) -> MaintenanceRunRead:
    return MaintenanceRunRead(
        id=run.id,
        kind=run.kind,
        status=run.status,
        progress=run.progress_json or {},
        result=run.result_json or {},
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
