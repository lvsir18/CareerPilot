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


def _create_application(client, job_id: str) -> dict:
    return client.post("/api/v1/applications", json={"job_id": job_id, "status": "applied"}).json()[
        "data"
    ]


def test_reschedule_supersedes_the_previous_slot(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    """UX3-02: "改期" must not leave the old appointment alive next to the new one."""
    job = _job(db_session, "推荐算法实习")
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="resched@example.com")
        created = _create_application(client, str(job.id))
        first = client.post(
            f"/api/v1/applications/{created['id']}/events",
            json={"status": "interview", "event_time": "2026-10-26T06:30:00+00:00"},
        ).json()["data"]
        second = client.post(
            f"/api/v1/applications/{created['id']}/events",
            json={
                "status": "interview",
                "event_time": "2026-10-27T06:30:00+00:00",
                "supersede_scheduled": True,
            },
        ).json()["data"]
        assert second["superseded_at"] is None

        calendar = client.get(
            "/api/v1/dashboard/calendar",
            params={"from": "2026-10-20T00:00:00+00:00", "to": "2026-11-30T00:00:00+00:00"},
        ).json()["data"]["events"]
        assert len(calendar) == 1
        assert calendar[0]["starts_at"].startswith("2026-10-27")

        detail = client.get(f"/api/v1/applications/{created['id']}").json()["data"]
        old = next(event for event in detail["events"] if event["id"] == first["id"])
        assert old["superseded_at"] is not None


def test_second_round_keeps_both_slots(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    """A genuinely new interview round must stay on the calendar."""
    job = _job(db_session, "数据开发实习")
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="rounds@example.com")
        created = _create_application(client, str(job.id))
        for when in ("2026-10-26T06:30:00+00:00", "2026-11-02T06:30:00+00:00"):
            client.post(
                f"/api/v1/applications/{created['id']}/events",
                json={"status": "interview", "event_time": when},
            )

        calendar = client.get(
            "/api/v1/dashboard/calendar",
            params={"from": "2026-10-20T00:00:00+00:00", "to": "2026-11-30T00:00:00+00:00"},
        ).json()["data"]["events"]
        assert len(calendar) == 2


def test_cancel_appointment_keeps_history(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    job = _job(db_session, "测试开发实习")
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="cancel-appt@example.com")
        created = _create_application(client, str(job.id))
        event = client.post(
            f"/api/v1/applications/{created['id']}/events",
            json={"status": "interview", "event_time": "2026-10-29T06:30:00+00:00"},
        ).json()["data"]

        cancelled = client.post(f"/api/v1/applications/{created['id']}/events/{event['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["superseded_at"] is not None

        calendar = client.get(
            "/api/v1/dashboard/calendar",
            params={"from": "2026-10-20T00:00:00+00:00", "to": "2026-11-30T00:00:00+00:00"},
        ).json()["data"]["events"]
        assert calendar == []

        detail = client.get(f"/api/v1/applications/{created['id']}").json()["data"]
        assert any(item["id"] == event["id"] for item in detail["events"])


def test_targeted_reschedule_preserves_other_round_and_rejects_ambiguous_request(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    job = _job(db_session, "多轮面试")
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="targeted-reschedule@example.com")
        created = _create_application(client, str(job.id))
        url = f"/api/v1/applications/{created['id']}/events"
        first, other = [
            client.post(url, json={"status": "interview", "event_time": when}).json()["data"]
            for when in ("2026-10-26T06:30:00Z", "2026-10-29T06:30:00Z")
        ]
        ambiguous = client.post(
            url,
            json={
                "status": "interview",
                "event_time": "2026-10-28T06:30:00Z",
                "supersede_scheduled": True,
            },
        )
        assert ambiguous.status_code == 409
        assert ambiguous.json()["error"]["code"] == "APPOINTMENT_SELECTION_REQUIRED"
        replacement = client.post(
            url,
            json={
                "status": "interview",
                "event_time": "2026-10-28T06:30:00Z",
                "reschedule_event_id": first["id"],
            },
        )
        assert replacement.status_code == 201
        detail = client.get(f"/api/v1/applications/{created['id']}").json()["data"]
        old = next(e for e in detail["events"] if e["id"] == first["id"])
        retained = next(e for e in detail["events"] if e["id"] == other["id"])
        assert old["superseded_at"] is not None
        assert retained["superseded_at"] is None
        calendar = client.get(
            "/api/v1/dashboard/calendar",
            params={
                "from": "2026-10-20T00:00:00Z",
                "to": "2026-11-01T00:00:00Z",
            },
        ).json()["data"]["events"]
        assert {e["id"] for e in calendar} == {replacement.json()["data"]["id"], other["id"]}
        stale = client.post(
            url,
            json={
                "status": "interview",
                "event_time": "2026-10-30T06:30:00Z",
                "reschedule_event_id": first["id"],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "APPOINTMENT_NOT_ACTIVE"
        wrong_kind = client.post(
            url,
            json={
                "status": "assessment",
                "event_time": "2026-10-30T06:30:00Z",
                "reschedule_event_id": other["id"],
            },
        )
        assert wrong_kind.status_code == 409
        missing_time = client.post(
            url, json={"status": "interview", "reschedule_event_id": other["id"]}
        )
        assert missing_time.status_code == 422
        after = client.get(f"/api/v1/applications/{created['id']}").json()["data"]
        assert len(after["events"]) == len(detail["events"])
        assert next(e for e in after["events"] if e["id"] == other["id"])["superseded_at"] is None


def test_reschedule_never_targets_another_users_event(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    job = _job(db_session, "预约隔离")
    with AutoCsrfTestClient(app, settings) as a, AutoCsrfTestClient(app, settings) as b:
        register_user(a, email="appointment-a@example.com")
        app_a = _create_application(a, str(job.id))
        event = a.post(
            f"/api/v1/applications/{app_a['id']}/events",
            json={
                "status": "interview",
                "event_time": "2026-10-26T06:30:00Z",
            },
        ).json()["data"]
        register_user(b, email="appointment-b@example.com")
        app_b = _create_application(b, str(job.id))
        payload = {
            "status": "interview",
            "event_time": "2026-10-28T06:30:00Z",
            "reschedule_event_id": event["id"],
        }
        assert b.post(f"/api/v1/applications/{app_a['id']}/events", json=payload).status_code == 404
        assert b.post(f"/api/v1/applications/{app_b['id']}/events", json=payload).status_code == 404
        unchanged = a.get(f"/api/v1/applications/{app_a['id']}").json()["data"]
        assert (
            next(e for e in unchanged["events"] if e["id"] == event["id"])["superseded_at"] is None
        )
