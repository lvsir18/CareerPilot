from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.job import Company, Job, JobSource
from app.db.seed import ensure_builtin_sources, seed_demo
from tests.factories import register_user


def test_seed_is_idempotent_and_marks_demo_data(db_session: Session) -> None:
    first = seed_demo(db_session)
    db_session.commit()

    assert first["jobs_created"] == 8
    assert first["total_jobs"] == 8
    assert first["is_demo"] is True

    second = seed_demo(db_session)
    db_session.commit()

    assert second["jobs_created"] == 0
    assert second["jobs_updated"] == 8
    assert db_session.scalar(select(func.count(Job.id))) == 8
    assert db_session.scalar(select(func.count(JobSource.id))) == 1
    assert db_session.scalar(select(func.count(Company.id))) == 3

    assert db_session.scalar(select(func.count(Job.id)).where(Job.is_demo.is_(False))) == 0
    assert db_session.scalar(select(func.count(Job.id)).where(Job.published_at.is_(None))) == 1

    jobs = list(db_session.scalars(select(Job)))
    assert all(job.source_id == jobs[0].source_id for job in jobs)
    assert all(job.source_url.startswith("https://demo.example.org/") for job in jobs)


def test_builtin_sources_are_idempotent_and_real_sources_stay_disabled(
    db_session: Session,
) -> None:
    first = ensure_builtin_sources(db_session)
    db_session.commit()
    second = ensure_builtin_sources(db_session)
    db_session.commit()

    assert len(first) == 4
    assert second == []
    sources = {source.source_key: source for source in db_session.scalars(select(JobSource))}
    assert sources["careerpilot-demo"].enabled is True
    assert sources["manual-import"].enabled is False
    assert sources["alibaba-careers"].enabled is False
    assert sources["baidu-public"].enabled is False


def test_demo_data_is_visible_in_demo_mode_and_hidden_in_production_mode(
    client: TestClient, non_demo_client: TestClient, db_session: Session
) -> None:
    seed_demo(db_session)
    db_session.commit()

    register_user(client, email="demo-viewer@example.com")
    demo_listing = client.get("/api/v1/jobs").json()
    assert demo_listing["meta"]["total"] == 8
    assert all(item["is_demo"] is True for item in demo_listing["data"])
    assert all(item["source_type"] == "fixture" for item in demo_listing["data"])

    register_user(non_demo_client, email="prod-viewer@example.com")
    real_listing = non_demo_client.get("/api/v1/jobs").json()
    assert real_listing["meta"]["total"] == 0
