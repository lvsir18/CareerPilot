from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.enums import JobStatus, SyncStatus
from app.db.models.job import Job, JobSource
from app.services.job_sync_service import JobSyncService


def _job_payload(
    *,
    source_job_id: str = "job-1",
    title: str = "Agent 工程师",
    company: str = "示例科技",
    city: str = "北京",
    status: str = "open",
    description: str = "负责 Agent 平台研发。",
) -> dict[str, Any]:
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "city": city,
        "location_text": f"{city}·测试区",
        "job_type": "校招",
        "recruitment_program": "2027届秋招",
        "description": description,
        "requirements": ["Python", "Agent"],
        "source_url": f"https://careers.example.com/jobs/{source_job_id}",
        "published_at": "2026-10-01T00:00:00Z",
        "status": status,
    }


def _write_jobs(path: Path, jobs: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False), encoding="utf-8")


def _source(
    session: Session,
    *,
    source_key: str,
    source_type: str = "manual",
    config: dict[str, Any] | None = None,
) -> JobSource:
    source = JobSource(
        source_type=source_type,
        source_key=source_key,
        config_json=config or {},
        enabled=True,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def _manual_settings(tmp_path: Path) -> Settings:
    return Settings(app_env="test", demo_mode=True, manual_import_dir=tmp_path)


def test_sync_upserts_idempotently_and_updates_changed_fields(
    db_session: Session, tmp_path: Path
) -> None:
    _write_jobs(tmp_path / "jobs.json", [_job_payload()])
    source = _source(db_session, source_key="manual-a", config={"filename": "jobs.json"})
    service = JobSyncService(db_session, _manual_settings(tmp_path))

    first = service.run(service.create_run(source.id, None).id)
    assert first.status == SyncStatus.SUCCESS
    assert first.created_count == 1
    assert first.fetched_count == 1
    assert first.failed_count == 0

    job = db_session.scalar(select(Job))
    assert job is not None
    assert job.duplicate_group_key
    assert float(job.first_seen_at.timestamp()) > 0
    first_seen = job.first_seen_at

    second = service.run(service.create_run(source.id, None).id)
    assert second.created_count == 0
    assert second.updated_count == 0
    assert second.unchanged_count == 1
    assert db_session.scalar(select(func.count(Job.id))) == 1

    _write_jobs(
        tmp_path / "jobs.json",
        [_job_payload(title="Agent 高级工程师", description="更新后的 JD")],
    )
    third = service.run(service.create_run(source.id, None).id)
    assert third.updated_count == 1
    db_session.refresh(job)
    assert job.title == "Agent 高级工程师"
    assert job.description == "更新后的 JD"
    assert job.first_seen_at == first_seen
    assert job.last_checked_at is not None


def test_unknown_status_does_not_close_job(db_session: Session, tmp_path: Path) -> None:
    _write_jobs(tmp_path / "jobs.json", [_job_payload(status="open")])
    source = _source(db_session, source_key="manual-status", config={"filename": "jobs.json"})
    service = JobSyncService(db_session, _manual_settings(tmp_path))
    service.run(service.create_run(source.id, None).id)
    job = db_session.scalar(select(Job))
    assert job is not None and job.status == JobStatus.OPEN

    _write_jobs(
        tmp_path / "jobs.json",
        [_job_payload(status="unknown", description="来源未给出状态")],
    )
    service.run(service.create_run(source.id, None).id)
    db_session.refresh(job)
    assert job.status == JobStatus.OPEN

    _write_jobs(
        tmp_path / "jobs.json",
        [_job_payload(status="closed", description="来源明确关闭")],
    )
    service.run(service.create_run(source.id, None).id)
    db_session.refresh(job)
    assert job.status == JobStatus.CLOSED


def test_cross_source_duplicates_are_grouped_not_merged(
    db_session: Session, tmp_path: Path
) -> None:
    _write_jobs(tmp_path / "a.json", [_job_payload(source_job_id="a-1")])
    _write_jobs(tmp_path / "b.json", [_job_payload(source_job_id="b-1")])
    source_a = _source(db_session, source_key="manual-a", config={"filename": "a.json"})
    source_b = _source(db_session, source_key="manual-b", config={"filename": "b.json"})
    service = JobSyncService(db_session, _manual_settings(tmp_path))

    service.run(service.create_run(source_a.id, None).id)
    service.run(service.create_run(source_b.id, None).id)

    jobs = list(db_session.scalars(select(Job).order_by(Job.source_job_id)))
    assert len(jobs) == 2
    assert jobs[0].duplicate_group_key == jobs[1].duplicate_group_key
    assert jobs[0].source_id != jobs[1].source_id


def test_invalid_rows_are_counted_and_failure_is_isolated(
    db_session: Session, tmp_path: Path
) -> None:
    invalid = _job_payload(source_job_id="bad-1")
    invalid["title"] = ""
    _write_jobs(tmp_path / "mixed.json", [_job_payload(), invalid])
    source = _source(db_session, source_key="manual-mixed", config={"filename": "mixed.json"})
    service = JobSyncService(db_session, _manual_settings(tmp_path))

    partial = service.run(service.create_run(source.id, None).id)

    assert partial.status == SyncStatus.PARTIAL
    assert partial.created_count == 1
    assert partial.failed_count == 1
    assert db_session.scalar(select(func.count(Job.id))) == 1

    broken = _source(db_session, source_key="manual-missing", config={"filename": "missing.json"})
    failed = service.run(service.create_run(broken.id, None).id)
    assert failed.status == SyncStatus.FAILED
    assert failed.error_message
    # Existing data from the healthy source is untouched.
    assert db_session.scalar(select(func.count(Job.id))) == 1


def test_demo_source_is_blocked_outside_demo_mode(db_session: Session, settings: Settings) -> None:
    source = _source(
        db_session,
        source_key="fixture-source",
        source_type="fixture",
        config={},
    )
    service = JobSyncService(db_session, settings.model_copy(update={"demo_mode": False}))

    run = service.run(service.create_run(source.id, None).id)

    assert run.status == SyncStatus.FAILED
    assert "DEMO_MODE" in (run.error_message or "")
    assert db_session.scalar(select(func.count(Job.id))) == 0


def test_sync_failure_does_not_close_existing_jobs(db_session: Session, tmp_path: Path) -> None:
    _write_jobs(tmp_path / "ok.json", [_job_payload(status="open")])
    source = _source(db_session, source_key="manual-ok", config={"filename": "ok.json"})
    service = JobSyncService(db_session, _manual_settings(tmp_path))
    service.run(service.create_run(source.id, None).id)
    job = db_session.scalar(select(Job))
    assert job is not None

    (tmp_path / "broken.json").write_text("{not-json", encoding="utf-8")
    broken_source = _source(
        db_session, source_key="manual-broken", config={"filename": "broken.json"}
    )
    broken_run = service.run(service.create_run(broken_source.id, None).id)

    assert broken_run.status == SyncStatus.FAILED
    db_session.refresh(job)
    assert job.status == JobStatus.OPEN
