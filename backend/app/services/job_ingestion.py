"""RawJob validation, normalization and idempotent upsert."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.schemas import RawJob
from app.core.text import normalize_company_name
from app.db.models.enums import (
    JobSourceMethod,
    JobStatus,
)
from app.db.models.job import Company, Job, JobSource

MAX_DESCRIPTION = 50_000
MAX_REQUIREMENTS = 100
MAX_REQUIREMENT_LENGTH = 2_000

_JOB_TYPE_ALIASES = {
    "internship": "internship",
    "实习": "internship",
    "日常实习": "internship",
    "暑期实习": "internship",
    "转正实习": "internship",
    "campus": "campus",
    "校招": "campus",
    "校园招聘": "campus",
    "应届": "campus",
    "春招": "campus",
    "秋招": "campus",
    "full_time": "full_time",
    "fulltime": "full_time",
    "全职": "full_time",
    "社招": "full_time",
    "part_time": "part_time",
    "兼职": "part_time",
    "contract": "contract",
    "合同制": "contract",
}


@dataclass(frozen=True)
class UpsertOutcome:
    created: bool = False
    updated: bool = False
    unchanged: bool = False


class InvalidRawJob(ValueError):
    pass


def normalize_job_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _JOB_TYPE_ALIASES.get(value.strip().lower())
    if normalized:
        return normalized
    return _JOB_TYPE_ALIASES.get(value.strip())


def normalize_text(value: str | None, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return None
    return cleaned[:limit] if limit else cleaned


def clean_text_block(value: str | None, *, limit: int) -> str | None:
    """Preserve JD line breaks; only trim outer whitespace and cap size."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def compute_content_hash(raw: RawJob) -> str:
    canonical = json.dumps(
        {
            "title": raw.title,
            "company": raw.company,
            "description": raw.description,
            "requirements": raw.requirements,
            "department": raw.department,
            "location_text": raw.location_text,
            "city": raw.city,
            "job_type": raw.job_type,
            "recruitment_program": raw.recruitment_program,
            "source_url": raw.source_url,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_duplicate_group_key(company: str, title: str, city: str | None) -> str:
    """Cross-source grouping key. Records are never merged or deleted."""
    material = "|".join(
        [
            normalize_company_name(company),
            re.sub(r"\s+", "", title).casefold(),
            re.sub(r"\s+", "", city or "").casefold(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _validate(raw: RawJob) -> None:
    if not raw.source_job_id.strip() or len(raw.source_job_id) > 200:
        raise InvalidRawJob("source_job_id 缺失或过长")
    if not raw.title.strip() or len(raw.title) > 300:
        raise InvalidRawJob("title 缺失或过长")
    if not raw.company.strip() or len(raw.company) > 200:
        raise InvalidRawJob("company 缺失或过长")
    parsed = urlsplit(raw.source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidRawJob("source_url 必须是 http/https")
    if raw.published_at is not None and raw.published_at.tzinfo is None:
        raise InvalidRawJob("published_at 必须带时区")


def _get_or_create_company(session: Session, name: str) -> Company:
    normalized = normalize_company_name(name)
    company = session.scalar(select(Company).where(Company.normalized_name == normalized))
    if company is None:
        company = Company(name=name.strip(), normalized_name=normalized)
        session.add(company)
        session.flush()
    return company


def _effective_source_method(raw: RawJob, source: JobSource) -> JobSourceMethod:
    if raw.source_method != JobSourceMethod.UNKNOWN:
        return raw.source_method
    if source.source_type == "fixture":
        return JobSourceMethod.FIXTURE
    if source.source_type == "manual":
        return JobSourceMethod.MANUAL_IMPORT
    if source.source_type in {"alibaba_openapi"}:
        return JobSourceMethod.API
    return JobSourceMethod.UNKNOWN


def upsert_raw_job(session: Session, source: JobSource, raw: RawJob) -> UpsertOutcome:
    _validate(raw)
    if raw.is_demo and not source.source_type == "fixture":
        raise InvalidRawJob("只有 fixture 连接器可以写入演示数据")
    source_method = _effective_source_method(raw, source)

    company = _get_or_create_company(session, raw.company.strip())
    existing = session.scalar(
        select(Job).where(Job.source_id == source.id, Job.source_job_id == raw.source_job_id)
    )

    requirements = [
        item.strip()[:MAX_REQUIREMENT_LENGTH]
        for item in raw.requirements[:MAX_REQUIREMENTS]
        if item and item.strip()
    ]
    content_hash = compute_content_hash(raw)
    duplicate_key = compute_duplicate_group_key(raw.company, raw.title, raw.city)
    now = datetime.now(UTC)
    status = raw.status if raw.status != JobStatus.UNKNOWN else None

    if existing is None:
        job = Job(
            source_id=source.id,
            source_job_id=raw.source_job_id.strip(),
            company_id=company.id,
            title=raw.title.strip()[:300],
            department=normalize_text(raw.department, limit=200),
            location_text=normalize_text(raw.location_text, limit=300),
            city=normalize_text(raw.city, limit=100),
            job_type=normalize_job_type(raw.job_type),
            recruitment_program=normalize_text(raw.recruitment_program, limit=100),
            description=clean_text_block(raw.description, limit=MAX_DESCRIPTION),
            requirements_json=requirements,
            source_url=raw.source_url.strip()[:1000],
            published_at=raw.published_at,
            first_seen_at=now,
            last_checked_at=raw.fetched_at,
            status=status or JobStatus.UNKNOWN,
            content_hash=content_hash,
            duplicate_group_key=duplicate_key,
            raw_payload_json=raw.raw_payload,
            is_demo=raw.is_demo,
            source_method=source_method,
            verification_status=raw.verification_status,
            verified_at=raw.verified_at,
        )
        session.add(job)
        session.flush()
        return UpsertOutcome(created=True)

    changed = existing.content_hash != content_hash
    if changed:
        existing.company_id = company.id
        existing.title = raw.title.strip()[:300]
        existing.department = normalize_text(raw.department, limit=200)
        existing.location_text = normalize_text(raw.location_text, limit=300)
        existing.city = normalize_text(raw.city, limit=100)
        existing.job_type = normalize_job_type(raw.job_type)
        existing.recruitment_program = normalize_text(raw.recruitment_program, limit=100)
        existing.description = clean_text_block(raw.description, limit=MAX_DESCRIPTION)
        existing.requirements_json = requirements
        existing.source_url = raw.source_url.strip()[:1000]
        existing.published_at = raw.published_at
        existing.content_hash = content_hash
        existing.raw_payload_json = raw.raw_payload
    existing.duplicate_group_key = duplicate_key
    existing.last_checked_at = raw.fetched_at
    existing.source_method = source_method
    existing.verification_status = raw.verification_status
    existing.verified_at = raw.verified_at
    # Absence from a fetch is not proof of closure: only an explicit source
    # status may change an existing job's state.
    if status is not None:
        existing.status = status

    return UpsertOutcome(updated=changed, unchanged=not changed)
