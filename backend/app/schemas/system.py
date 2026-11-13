"""Pydantic response contracts for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(examples=["NOT_FOUND"])
    message: str = Field(examples=["资源不存在"])
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    demo_mode: bool


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "error"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    checks: list[DependencyStatus]
    checked_at: datetime


class SystemInfoResponse(BaseModel):
    """Non-sensitive runtime metadata for the dashboard."""

    app_name: str
    version: str
    app_env: str
    demo_mode: bool
    execution_mode: Literal["llm", "rule_fallback"]
    llm_configured: bool
    public_connectors_enabled: bool
    job_sync_enabled: bool
    api_docs_url: str


class JobMaintenanceActivity(BaseModel):
    run_id: UUID
    kind: str
    status: str
    total: int = 0
    processed: int = 0


class AgentActivity(BaseModel):
    run_id: UUID
    thread_id: UUID
    status: str


class ActivityResponse(BaseModel):
    """What this user has running in the background right now.

    The sidebar polls this so a long job refresh or agent turn keeps showing a
    spinner after the user navigates to another page.
    """

    job_maintenance: JobMaintenanceActivity | None = None
    agent: AgentActivity | None = None
