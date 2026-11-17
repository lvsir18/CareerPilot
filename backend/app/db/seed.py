"""Idempotent demo fixture importer.

Every row written here is ``is_demo=true`` and points at ``demo.example.org``.
Production refuses to run this importer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.text import normalize_company_name
from app.db.models.enums import JobStatus
from app.db.models.job import Company, Job, JobSource
from app.db.session import session_scope

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "demo_jobs.json"

logger = get_logger(__name__)


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_or_create_company(session: Session, name: str, website: str | None) -> Company:
    normalized = normalize_company_name(name)
    company = session.scalar(select(Company).where(Company.normalized_name == normalized))
    if company is None:
        company = Company(name=name, normalized_name=normalized, website=website)
        session.add(company)
        session.flush()
    return company


def seed_demo(session: Session) -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    source_config = payload["source"]

    source = session.scalar(
        select(JobSource).where(
            JobSource.source_type == source_config["source_type"],
            JobSource.source_key == source_config["source_key"],
        )
    )
    if source is None:
        source = JobSource(
            source_type=source_config["source_type"],
            source_key=source_config["source_key"],
            config_json=source_config.get("config", {}),
        )
        session.add(source)
        session.flush()

    created = 0
    updated = 0
    for item in payload["jobs"]:
        company = _get_or_create_company(session, item["company"], item.get("company_website"))
        content_hash = _content_hash(
            {
                "title": item["title"],
                "company": item["company"],
                "description": item.get("description"),
                "requirements": item.get("requirements", []),
                "source_url": item["source_url"],
                "location_text": item.get("location_text"),
                "job_type": item.get("job_type"),
            }
        )
        job = session.scalar(
            select(Job).where(
                Job.source_id == source.id,
                Job.source_job_id == item["source_job_id"],
            )
        )
        if job is None:
            job = Job(
                source_id=source.id,
                source_job_id=item["source_job_id"],
                company_id=company.id,
                title=item["title"],
                description=item.get("description"),
                requirements_json=item.get("requirements", []),
                source_url=item["source_url"],
                content_hash=content_hash,
                is_demo=True,
                source_method="fixture",
                verification_status="unverified",
            )
            session.add(job)
            created += 1
        else:
            updated += 1

        job.company_id = company.id
        job.title = item["title"]
        job.location_text = item.get("location_text")
        job.city = item.get("city")
        job.job_type = item.get("job_type")
        job.description = item.get("description")
        job.requirements_json = item.get("requirements", [])
        job.source_url = item["source_url"]
        job.source_method = "fixture"
        job.verification_status = "unverified"
        job.published_at = (
            datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            if item.get("published_at")
            else None
        )
        job.status = JobStatus(item.get("status", "unknown"))
        job.content_hash = content_hash
        job.is_demo = True
        job.last_checked_at = datetime.now(UTC)

    session.flush()
    total = session.scalar(select(func.count(Job.id)).where(Job.source_id == source.id)) or 0

    summary = {
        "source_id": str(source.id),
        "source_key": source.source_key,
        "jobs_created": created,
        "jobs_updated": updated,
        "total_jobs": int(total),
        "is_demo": True,
    }
    logger.info("demo_seed_completed", extra=summary)
    return summary


def ensure_builtin_sources(session: Session) -> list[str]:
    """Create the built-in source rows without importing any job data.

    Real sources stay disabled until an administrator configures and enables
    them; no credentials are stored in ``config_json``.
    """
    specs = (
        ("fixture", "careerpilot-demo", True, {}),
        ("manual", "manual-import", False, {"filename": "jobs.json"}),
        ("alibaba_openapi", "alibaba-careers", False, {}),
        ("baidu_public", "baidu-public", False, {}),
    )
    created: list[str] = []
    for source_type, source_key, enabled, config in specs:
        existing = session.scalar(
            select(JobSource).where(
                JobSource.source_type == source_type, JobSource.source_key == source_key
            )
        )
        if existing is None:
            session.add(
                JobSource(
                    source_type=source_type,
                    source_key=source_key,
                    config_json=config,
                    enabled=enabled,
                )
            )
            created.append(f"{source_type}:{source_key}")
    session.flush()
    return created


def main() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.is_production:
        raise SystemExit("拒绝在生产环境导入 Demo 数据（APP_ENV=production）")

    with session_scope() as session:
        summary = seed_demo(session)
        summary["sources_created"] = ensure_builtin_sources(session)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
