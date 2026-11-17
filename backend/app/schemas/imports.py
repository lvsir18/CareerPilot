"""Contracts for user-initiated official job link imports."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.connectors.schemas import RawJob
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus


class ImportPreviewRequest(BaseModel):
    url: HttpUrl


class ImportPreview(BaseModel):
    source_url: str
    source_job_id: str
    company: str
    title: str
    department: str | None
    city: str | None
    location_text: str | None
    job_type: str | None
    recruitment_program: str | None
    description: str | None
    requirements: list[str]
    published_at: datetime | None
    status: JobStatus
    source_method: JobSourceMethod
    verification_status: VerificationStatus
    verified_at: datetime | None
    warnings: list[str] = Field(default_factory=list)


class JobImportRequest(BaseModel):
    url: HttpUrl
    mode: Literal["public_page", "manual_paste"] = "public_page"
    confirmed: bool = False

    # Required only for manual_paste.
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=50_000)
    requirements: list[str] = Field(default_factory=list, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    location_text: str | None = Field(default=None, max_length=300)
    job_type: str | None = Field(default=None, max_length=50)
    recruitment_program: str | None = Field(default=None, max_length=100)
    published_at: datetime | None = None


class ImportResult(BaseModel):
    job_id: UUID
    created: bool
    updated: bool
    verification_status: VerificationStatus


def preview_from_raw(raw: RawJob) -> ImportPreview:
    warnings: list[str] = []
    if raw.published_at is not None:
        warnings.append("官方页面仅提供日期，发布时间按 UTC 00:00 记录")
    if not raw.requirements:
        warnings.append("页面未提供任职要求，未做推测")
    return ImportPreview(
        source_url=raw.source_url,
        source_job_id=raw.source_job_id,
        company=raw.company,
        title=raw.title,
        department=raw.department,
        city=raw.city,
        location_text=raw.location_text,
        job_type=raw.job_type,
        recruitment_program=raw.recruitment_program,
        description=raw.description,
        requirements=raw.requirements,
        published_at=raw.published_at,
        status=raw.status,
        source_method=raw.source_method,
        verification_status=raw.verification_status,
        verified_at=raw.verified_at,
        warnings=warnings,
    )
