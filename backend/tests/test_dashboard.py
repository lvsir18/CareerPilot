from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.enums import JobSourceMethod, VerificationStatus
from app.db.models.job import Company, Job, JobSource
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user


def _job(session: Session, title: str) -> Job:
    company = Company(name="测试科技", normalized_name="测试科技")
    session.add(company)
    source = JobSource(source_type="test", source_key="dash-source", config_json={}, enabled=True)
    session.add(source)
    session.flush()
    job = Job(
        source_id=source.id,
        source_job_id=title,
        company_id=company.id,
        title=title,
        source_url="https://example.com/job",
        content_hash=f"hash-{title}",
        source_method=JobSourceMethod.PUBLIC_PAGE,
        verification_status=VerificationStatus.VERIFIED,
        is_demo=False,
    )
    session.add(job)
    session.commit()
    return job


def test_dashboard_counts_reflect_user_data(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    job = _job(db_session, "大模型算法实习生")
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="dash@example.com")

        empty = client.get("/api/v1/dashboard/summary")
        assert empty.status_code == 200
        counts = empty.json()["data"]["counts"]
        assert counts["saved"] == 0
        assert counts["applied"] == 0

        client.post(f"/api/v1/jobs/{job.id}/save", json={"list_type": "saved"})
        client.post("/api/v1/applications", json={"job_id": str(job.id), "status": "applied"})

        summary = client.get("/api/v1/dashboard/summary").json()["data"]
        assert summary["counts"]["saved"] == 1
        assert summary["counts"]["applied"] == 1
        assert summary["latest_jobs"]


def test_calendar_lists_only_explicit_appointments(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    job = _job(db_session, "大模型算法实习生")
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="cal@example.com")
        created = client.post(
            "/api/v1/applications", json={"job_id": str(job.id), "status": "applied"}
        ).json()["data"]
        # A status change with a timestamp is still not an appointment.
        client.post(
            f"/api/v1/applications/{created['id']}/events",
            json={"status": "applied", "event_time": "2026-10-26T01:00:00+00:00"},
        )
        client.post(
            f"/api/v1/applications/{created['id']}/events",
            json={"status": "interview", "event_time": "2026-10-28T02:00:00+00:00"},
        )
        client.post(
            f"/api/v1/applications/{created['id']}/events",
            json={"status": "interview", "event_time": "2027-03-01T02:00:00+00:00"},
        )

        response = client.get(
            "/api/v1/dashboard/calendar",
            params={"from": "2026-10-01T00:00:00+00:00", "to": "2026-11-01T00:00:00+00:00"},
        )
        assert response.status_code == 200
        events = response.json()["data"]["events"]
        assert [event["status"] for event in events] == ["interview"]
        assert events[0]["starts_at"].startswith("2026-10-28")
        assert events[0]["company"] == "测试科技"


def test_calendar_is_user_scoped(app: FastAPI, settings: Settings, db_session: Session) -> None:
    job = _job(db_session, "数据开发实习")
    with AutoCsrfTestClient(app, settings) as client_a:
        register_user(client_a, email="cal-a@example.com")
        created = client_a.post(
            "/api/v1/applications", json={"job_id": str(job.id), "status": "applied"}
        ).json()["data"]
        client_a.post(
            f"/api/v1/applications/{created['id']}/events",
            json={"status": "interview", "event_time": "2026-10-29T02:00:00+00:00"},
        )

        client_b = AutoCsrfTestClient(app, settings)
        register_user(client_b, email="cal-b@example.com")
        response = client_b.get(
            "/api/v1/dashboard/calendar",
            params={"from": "2026-10-01T00:00:00+00:00", "to": "2026-11-01T00:00:00+00:00"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["events"] == []


def test_dashboard_is_user_scoped(app: FastAPI, settings: Settings, db_session: Session) -> None:
    job = _job(db_session, "后端开发实习")
    with AutoCsrfTestClient(app, settings) as client_a:
        register_user(client_a, email="dash-a@example.com")
        client_a.post("/api/v1/applications", json={"job_id": str(job.id), "status": "applied"})

        client_b = AutoCsrfTestClient(app, settings)
        register_user(client_b, email="dash-b@example.com")
        summary = client_b.get("/api/v1/dashboard/summary").json()["data"]
        assert summary["counts"]["applied"] == 0


def test_calendar_ignores_status_change_when_no_time_given(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    """A status flip to ``interview`` stamps ``event_time=now``; that is not a slot."""
    job = _job(db_session, "推荐算法实习")
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="cal-status@example.com")
        created = client.post(
            "/api/v1/applications", json={"job_id": str(job.id), "status": "applied"}
        ).json()["data"]
        client.patch(f"/api/v1/applications/{created['id']}", json={"status": "interview"})

        response = client.get(
            "/api/v1/dashboard/calendar",
            params={"from": "2026-10-01T00:00:00+00:00", "to": "2026-12-01T00:00:00+00:00"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["events"] == []
