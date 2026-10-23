"""Job response contracts and ORM mapping helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus
from app.db.models.job import Job
from app.schemas.evidence import SourceEvidenceRead
from app.search.taxonomy import classify_job_family

JobSort = Literal["published_at_desc", "first_seen_at_desc", "title_asc"]


class JobListItem(BaseModel):
    id: UUID
    company: str
    title: str
    department: str | None
    city: str | None
    location_text: str | None
    job_type: str | None
    recruitment_program: str | None
    source_type: str
    source_key: str
    source_url: str
    published_at: datetime | None
    first_seen_at: datetime
    status: JobStatus
    is_demo: bool
    source_method: JobSourceMethod
    verification_status: VerificationStatus
    verified_at: datetime | None
    job_family: str


class JobDetail(JobListItem):
    description: str | None
    requirements: list[str]
    skills: list[str] = []
    official_job_id: str | None = None
    last_checked_at: datetime | None
    evidence: list[SourceEvidenceRead] = []


def job_to_list_item(job: Job) -> JobListItem:
    return JobListItem(
        id=job.id,
        company=job.company.name,
        title=job.title,
        department=job.department,
        city=job.city,
        location_text=job.location_text,
        job_type=job.job_type,
        recruitment_program=job.recruitment_program,
        source_type=job.source.source_type,
        source_key=job.source.source_key,
        source_url=job.source_url,
        published_at=job.published_at,
        first_seen_at=job.first_seen_at,
        status=job.status,
        is_demo=job.is_demo,
        source_method=job.source_method,
        verification_status=job.verification_status,
        verified_at=job.verified_at,
        job_family=classify_job_family(job.title, job.description),
    )


def job_to_detail(job: Job, evidence: list[SourceEvidenceRead] | None = None) -> JobDetail:
    base = job_to_list_item(job)
    return JobDetail(
        **base.model_dump(),
        description=job.description,
        requirements=list(job.requirements_json or []),
        skills=list((job.raw_payload_json or {}).get("skills", [])),
        official_job_id=(job.raw_payload_json or {}).get("official_job_id"),
        last_checked_at=job.last_checked_at,
        evidence=evidence or [],
    )
