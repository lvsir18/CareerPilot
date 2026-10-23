"""Pydantic response contracts for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
