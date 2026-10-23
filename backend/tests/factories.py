"""Test data factories (explicitly non-demo unless requested)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.text import normalize_company_name
from app.db.models.enums import JobStatus
from app.db.models.job import Company, Job, JobSource


def create_job(session: Session, **overrides: Any) -> Job:
    source_job_id = overrides.pop("source_job_id", f"test-{uuid4().hex}")
    company_name = overrides.pop("company", "Acme 测试公司")
    source_type = overrides.pop("source_type", "manual")
    source_key = overrides.pop("source_key", "test-manual")

    normalized = normalize_company_name(company_name)
    company = session.scalar(select(Company).where(Company.normalized_name == normalized))
    if company is None:
        company = Company(name=company_name, normalized_name=normalized)
        session.add(company)
        session.flush()

    source = session.scalar(
        select(JobSource).where(
            JobSource.source_type == source_type, JobSource.source_key == source_key
        )
    )
    if source is None:
        source = JobSource(
            source_type=source_type, source_key=source_key, config_json={}, enabled=True
        )
        session.add(source)
        session.flush()

    title = overrides.pop("title", "Agent 算法实习生")
    job = Job(
        source_id=source.id,
        source_job_id=source_job_id,
        company_id=company.id,
        title=title,
        description=overrides.pop("description", "负责 LLM Agent 相关研发。"),
        requirements_json=overrides.pop("requirements", ["Python", "LLM"]),
        source_url=overrides.pop("source_url", f"https://jobs.example.test/{source_job_id}"),
        published_at=overrides.pop("published_at", datetime(2026, 10, 18, 9, tzinfo=UTC)),
        first_seen_at=overrides.pop("first_seen_at", datetime(2026, 10, 19, 9, tzinfo=UTC)),
        last_checked_at=overrides.pop("last_checked_at", datetime(2026, 10, 20, 9, tzinfo=UTC)),
        status=overrides.pop("status", JobStatus.OPEN),
        content_hash=hashlib.sha256(source_job_id.encode()).hexdigest(),
        is_demo=overrides.pop("is_demo", False),
        city=overrides.pop("city", "上海"),
        location_text=overrides.pop("location_text", "上海·浦东"),
        job_type=overrides.pop("job_type", "internship"),
        **overrides,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def register_user(
    client, email: str | None = None, password: str = "strong-pass-123"
) -> dict[str, Any]:
    email = email or f"user-{uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return {"email": email, "password": password, "body": response.json()["data"]}


def job_uuid(job: Job) -> UUID:
    return job.id
