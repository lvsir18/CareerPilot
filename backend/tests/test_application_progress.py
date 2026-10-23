from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.application import ApplicationEvent
from app.db.models.application_import import ApplicationImport
from app.db.models.enums import ApplicationStatus
from app.services.email_parser import parse_eml
from app.services.job_lead_service import JobLeadService
from tests.conftest import AutoCsrfTestClient
from tests.factories import create_job, register_user

BAIDU_URL = "https://talent.baidu.com/jobs/detail/INTERN/f8f8f186-2d4a-4b55-9f6c-34018f476896"


def _eml(
    *,
    subject: str,
    body: str,
    sender: str = "百度招聘 <talent@baidu.com>",
    date: datetime | None = None,
) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = "candidate@example.com"
    message["Date"] = format_datetime(date or datetime(2026, 10, 21, 9, 0, tzinfo=UTC))
    message.set_content(body)
    return message.as_bytes()


def _register_and_job(
    client: TestClient, session: Session, *, company="百度", title="Agent策略工程师"
):
    registered = register_user(client)
    job = create_job(
        session,
        company=company,
        title=title,
        description="负责 Agent 策略研发。",
        is_demo=False,
    )
    return registered, job


def _create_application(client: TestClient, job_id) -> dict:
    response = client.post(
        "/api/v1/applications",
        json={"job_id": str(job_id), "status": "applied"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_link_only_and_lead_applications_are_deduplicated_and_isolated(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as user_a:
        registered, _job = _register_and_job(user_a, db_session)
        user_id = registered["body"]["id"]
        lead = JobLeadService(db_session, settings).import_private(
            user_id=user_id,
            url=BAIDU_URL,
            title="Agent策略工程师（候选）",
            description="用户导入的 JD",
        )

        from_lead = user_a.post(
            "/api/v1/applications",
            json={"job_lead_id": str(lead.id), "status": "planned"},
        )
        assert from_lead.status_code == 201
        lead_data = from_lead.json()["data"]
        assert lead_data["job"] is None
        assert lead_data["lead"]["id"] == str(lead.id)
        assert lead_data["external_company"] == "百度"

        duplicate = user_a.post(
            "/api/v1/applications",
            json={"job_lead_id": str(lead.id), "status": "planned"},
        )
        assert duplicate.status_code == 409

        link_only = user_a.post(
            "/api/v1/applications",
            json={
                "external_url": BAIDU_URL,
                "external_company": "百度",
                "external_title": "仅官方链接登记的岗位",
                "status": "saved",
            },
        )
        assert link_only.status_code == 201
        link_data = link_only.json()["data"]
        assert link_data["job"] is None
        assert link_data["lead"] is None
        assert link_data["external_title"] == "仅官方链接登记的岗位"
        assert link_data["status"] == "saved"

        filtered = user_a.get("/api/v1/applications", params={"query": "仅官方链接"}).json()
        assert filtered["meta"]["total"] == 1

    with AutoCsrfTestClient(app, settings) as user_b:
        register_user(user_b, email="progress-b@example.com")
        assert user_b.get(f"/api/v1/applications/{lead_data['id']}").status_code == 404
        denied_lead = user_b.post(
            "/api/v1/applications",
            json={"job_lead_id": str(lead.id), "status": "planned"},
        )
        assert denied_lead.status_code == 404


def test_opening_job_detail_does_not_create_an_application(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        _registered, job = _register_and_job(client, db_session)
        detail = client.get(f"/api/v1/jobs/{job.id}")
        assert detail.status_code == 200
        applications = client.get("/api/v1/applications").json()
        assert applications["meta"]["total"] == 0


def test_long_unconfirmed_application_is_flagged_for_review(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        _registered, job = _register_and_job(client, db_session)
        application = _create_application(client, job.id)
        from datetime import timedelta

        from app.db.models.application import Application

        row = db_session.get(Application, application["id"])
        assert row is not None
        row.last_confirmed_at = datetime.now(UTC) - timedelta(days=20)
        db_session.commit()

        listed = client.get("/api/v1/applications").json()["data"]
        assert listed[0]["needs_review"] is True
        assert listed[0]["stale_days"] >= 20
        assert listed[0]["status"] == "applied"


def test_events_preserve_history_and_dedupe_source_reference(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        _registered, job = _register_and_job(client, db_session)
        application = _create_application(client, job.id)

        first = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "status": "screening",
                "event_time": "2026-10-22T09:00:00Z",
                "evidence_summary": "用户从官网看到筛选中",
                "source_reference": "manual-page-1",
            },
        )
        assert first.status_code == 201
        event_id = first.json()["data"]["id"]
        assert first.json()["data"]["verification_status"] == "user_reported"

        duplicate = client.post(
            f"/api/v1/applications/{application['id']}/events",
            json={
                "status": "screening",
                "source_reference": "manual-page-1",
            },
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["data"]["id"] == event_id

        corrected = client.patch(
            f"/api/v1/applications/{application['id']}/status",
            json={"status": "interview", "note": "用户纠正为面试中"},
        )
        assert corrected.status_code == 200
        assert corrected.json()["data"]["status"] == "interview"

        detail = client.get(f"/api/v1/applications/{application['id']}").json()["data"]
        transitions = [(e["from_status"], e["to_status"]) for e in detail["events"]]
        assert ("applied", "screening") in transitions
        assert ("screening", "interview") in transitions
        assert detail["latest_event"]["source_type"] == "manual"

    assert (
        len(list(db_session.scalars(select(ApplicationEvent)))) == 3
    )  # initial + screening + interview; duplicate did not add one


def test_email_import_requires_preview_and_confirmation(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        _registered, job = _register_and_job(client, db_session)
        application = _create_application(client, job.id)
        raw = _eml(
            subject="【百度】面试邀请 - Agent策略工程师",
            body=(
                "您好，您申请的 Agent策略工程师 已进入面试环节。\n面试时间：2026年10月25日 14:00。"
            ),
        )

        preview = client.post(
            "/api/v1/application-imports/email",
            files={"file": ("interview.eml", raw, "message/rfc822")},
        )
        assert preview.status_code == 201, preview.text
        data = preview.json()["data"]
        assert data["duplicate"] is False
        assert data["parsed_status"] == "interview"
        assert data["matched_application_id"] == application["id"]
        assert data["status"] == "ready"
        assert data["parsed_event_time"].startswith("2026-10-25T14:00")
        assert len(list(db_session.scalars(select(ApplicationEvent)))) == 1

        confirmed = client.post(f"/api/v1/application-imports/{data['id']}/confirm", json={})
        assert confirmed.status_code == 200
        assert confirmed.json()["data"]["status"] == "confirmed"

        application_after = client.get(f"/api/v1/applications/{application['id']}").json()["data"]
        assert application_after["status"] == "interview"
        email_event = application_after["events"][-1]
        assert email_event["source_type"] == "email_import"
        assert email_event["verification_status"] == "email_confirmed"

        again = client.post(f"/api/v1/application-imports/{data['id']}/confirm", json={})
        assert again.status_code == 200
        assert len(list(db_session.scalars(select(ApplicationEvent)))) == 2

        duplicate = client.post(
            "/api/v1/application-imports/email",
            files={"file": ("interview.eml", raw, "message/rfc822")},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["data"]["id"] == data["id"]
        assert duplicate.json()["data"]["duplicate"] is True
        assert len(list(db_session.scalars(select(ApplicationImport)))) == 1

    with AutoCsrfTestClient(app, settings) as user_b:
        register_user(user_b, email="email-b@example.com")
        assert user_b.get(f"/api/v1/application-imports/{data['id']}").status_code == 404
        assert (
            user_b.post(f"/api/v1/application-imports/{data['id']}/confirm", json={}).status_code
            == 404
        )


def test_ambiguous_email_does_not_update_without_explicit_user_status(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        _registered, job = _register_and_job(client, db_session)
        application = _create_application(client, job.id)
        raw = _eml(
            subject="简历已接收 - Agent策略工程师",
            body="我们已收到您的简历，后续安排将另行通知。",
        )
        preview = client.post(
            "/api/v1/application-imports/email",
            files={"file": ("received.eml", raw, "message/rfc822")},
        )
        assert preview.status_code == 201
        data = preview.json()["data"]
        assert data["parsed_status"] is None
        assert data["status"] == "needs_review"
        assert any("收到简历" in warning for warning in data["warnings"])

        refused = client.post(f"/api/v1/application-imports/{data['id']}/confirm", json={})
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "APPLICATION_STATUS_REQUIRED"

        confirmed = client.post(
            f"/api/v1/application-imports/{data['id']}/confirm",
            json={"application_id": application["id"], "status": "applied"},
        )
        assert confirmed.status_code == 200
        events = client.get(f"/api/v1/applications/{application['id']}").json()["data"]["events"]
        email_events = [event for event in events if event["source_type"] == "email_import"]
        assert len(email_events) == 1
        assert email_events[0]["verification_status"] == "user_reported"


def test_email_parser_strips_html_and_scripts() -> None:
    message = EmailMessage()
    message["Subject"] = "【百度】面试邀请"
    message["From"] = "百度招聘 <talent@baidu.com>"
    message["Date"] = format_datetime(datetime(2026, 10, 21, 9, 0, tzinfo=UTC))
    message.set_content(
        "<html><body><script>alert(1)</script><p>进入面试</p>"
        '<img src="https://evil.test/x.png"></body></html>',
        subtype="html",
    )
    parsed = parse_eml(message.as_bytes())
    assert "alert(1)" not in (parsed.body_excerpt or "")
    assert "进入面试" in (parsed.body_excerpt or "")
    assert parsed.status == ApplicationStatus.INTERVIEW


def test_email_import_rejects_wrong_type_and_oversize(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="email-type@example.com")
        wrong = client.post(
            "/api/v1/application-imports/email",
            files={"file": ("resume.txt", b"not an email", "text/plain")},
        )
        assert wrong.status_code == 422
        assert wrong.json()["error"]["code"] == "INVALID_EMAIL_FILE"

        too_large = client.post(
            "/api/v1/application-imports/email",
            files={"file": ("huge.eml", b"x" * (2 * 1024 * 1024 + 1), "message/rfc822")},
        )
        assert too_large.status_code == 413
