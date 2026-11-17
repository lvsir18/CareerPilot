from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.job_syncs as sync_api
from app.core.config import Settings
from app.db.models.job import JobSource
from app.services.job_sync_service import JobSyncService
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user


def _manual_source(session: Session, tmp_path: Path, key: str = "manual-api") -> JobSource:
    (tmp_path / "jobs.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "source_job_id": "api-1",
                        "company": "示例公司",
                        "title": "Agent 工程师",
                        "city": "北京",
                        "job_type": "campus",
                        "description": "负责 Agent 平台。",
                        "requirements": ["Python"],
                        "source_url": "https://careers.example.com/jobs/api-1",
                        "published_at": "2026-10-01T00:00:00Z",
                        "status": "open",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    source = JobSource(
        source_type="manual",
        source_key=key,
        config_json={"filename": "jobs.json"},
        enabled=True,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


class _ImmediateTask:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory

    def delay(self, run_id: str) -> None:
        with self.session_factory() as session:
            JobSyncService(session, self.settings).run(UUID(run_id))


class _BrokenTask:
    def delay(self, run_id: str) -> None:
        raise RuntimeError("broker down")


def test_sync_requires_admin(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    session_factory: sessionmaker[Session],
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _manual_source(db_session, tmp_path)
    register_user(client, email="normal@example.com")
    monkeypatch.setattr(sync_api, "sync_job_source", _ImmediateTask(settings, session_factory))

    response = client.post("/api/v1/job-syncs", json={"source_id": str(source.id)})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_admin_can_trigger_sync_and_observe_result(
    app: FastAPI,
    settings: Settings,
    session_factory: sessionmaker[Session],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = JobSource(
        source_type="fixture",
        source_key="fixture-api",
        config_json={},
        enabled=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    monkeypatch.setattr(sync_api, "sync_job_source", _ImmediateTask(settings, session_factory))

    with AutoCsrfTestClient(app, settings) as admin:
        register_user(admin, email="admin@example.com")

        listed = admin.get("/api/v1/job-sources")
        assert listed.status_code == 200
        assert any(item["id"] == str(source.id) for item in listed.json()["data"])

        health = admin.get(f"/api/v1/job-sources/{source.id}/health")
        assert health.status_code == 200
        assert health.json()["data"]["configured"] is True

        trigger = admin.post("/api/v1/job-syncs", json={"source_id": str(source.id)})
        assert trigger.status_code == 202
        run_id = trigger.json()["data"]["id"]

        run = admin.get(f"/api/v1/job-syncs/{run_id}")
        assert run.status_code == 200
        body = run.json()["data"]
        assert body["status"] == "success"
        assert body["created_count"] == 8

        listing = admin.get("/api/v1/job-syncs")
        assert listing.status_code == 200
        assert listing.json()["meta"]["total"] == 1

        jobs = admin.get("/api/v1/jobs", params={"source_types": "fixture"}).json()
        assert jobs["meta"]["total"] == 8
        assert jobs["data"][0]["is_demo"] is True


def test_queue_failure_marks_run_failed(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _manual_source(db_session, tmp_path)
    monkeypatch.setattr(sync_api, "sync_job_source", _BrokenTask())

    with AutoCsrfTestClient(app, settings) as admin:
        register_user(admin, email="admin@example.com")
        response = admin.post("/api/v1/job-syncs", json={"source_id": str(source.id)})

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SYNC_QUEUE_UNAVAILABLE"

        runs = admin.get("/api/v1/job-syncs").json()["data"]
        assert len(runs) == 1
        assert runs[0]["status"] == "failed"


def test_source_config_is_admin_only_and_allowlisted(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    tmp_path: Path,
) -> None:
    source = _manual_source(db_session, tmp_path)

    with AutoCsrfTestClient(app, settings) as normal:
        register_user(normal, email="normal2@example.com")
        denied = normal.patch(f"/api/v1/job-sources/{source.id}", json={"enabled": False})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "ADMIN_REQUIRED"

    with AutoCsrfTestClient(app, settings) as admin:
        register_user(admin, email="admin@example.com")

        invalid = admin.patch(
            f"/api/v1/job-sources/{source.id}",
            json={"config": {"filename": "jobs.json", "app_secret": "secret"}},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_SOURCE_CONFIG"

        updated = admin.patch(
            f"/api/v1/job-sources/{source.id}",
            json={"enabled": False, "config": {"filename": "jobs.json"}},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["enabled"] is False


def test_disabled_source_cannot_be_triggered(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    tmp_path: Path,
) -> None:
    source = _manual_source(db_session, tmp_path, key="disabled-source")
    source.enabled = False
    db_session.commit()

    with AutoCsrfTestClient(app, settings) as admin:
        register_user(admin, email="admin@example.com")
        response = admin.post("/api/v1/job-syncs", json={"source_id": str(source.id)})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_SOURCE_DISABLED"
