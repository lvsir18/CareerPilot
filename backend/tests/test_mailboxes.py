from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.mailbox import RecruitmentEventCandidate
from app.services.mailbox_connectors import MailboxMessage
from app.services.mailbox_secret import decrypt_secret, encrypt_secret
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user

EML = """From: hr@testcorp.com
To: user@example.com
Subject: 面试邀请 - 大模型算法实习生
Date: Thu, 22 Oct 2026 10:00:00 +0800
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

您好，邀请您参加大模型算法实习生岗位的面试。面试时间：2026-10-25 14:00。
""".encode()


def _enable_secret(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "mailbox_secret_key", key)
    return key


def test_secret_roundtrip_and_requires_key(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AppError):
        encrypt_secret(settings, {"auth_code": "x"})

    _enable_secret(settings, monkeypatch)
    token = encrypt_secret(settings, {"auth_code": "abcd"})
    assert "abcd" not in token
    assert decrypt_secret(settings, token)["auth_code"] == "abcd"


def test_qq_connect_is_encrypted_and_listed(
    app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_secret(settings, monkeypatch)

    class FakeQQ:
        def __init__(self, _settings: Settings) -> None:
            pass

        def test_connection(self, email, code) -> None:
            return None

    monkeypatch.setattr("app.api.v1.mailboxes.QQIMAPConnector", FakeQQ)
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="mailbox-qq@example.com")
        response = client.post(
            "/api/v1/mailboxes/qq/connect",
            json={"email_address": "tester@qq.com", "auth_code": "secret-code-123"},
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["provider"] == "qq_imap"
        assert data["status"] == "active"
        assert "secret-code-123" not in response.text

        listed = client.get("/api/v1/mailboxes").json()["data"]
        assert len(listed) == 1
        assert listed[0]["email_address"] == "tester@qq.com"


def test_sync_generates_candidate_and_is_idempotent(
    app: FastAPI, settings: Settings, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_secret(settings, monkeypatch)

    message = MailboxMessage(
        provider="qq_imap",
        provider_message_id="msg-1",
        subject="面试邀请",
        sender="hr@testcorp.com",
        received_at=datetime.now(UTC),
        raw=EML,
    )

    class FakeQQ:
        def __init__(self, _settings: Settings) -> None:
            pass

        def test_connection(self, email, code) -> None:
            return None

        def list_messages(self, *args, **kwargs):
            return [message], {"imap_uidvalidity": 1, "imap_last_uid": 10}

    monkeypatch.setattr("app.api.v1.mailboxes.QQIMAPConnector", FakeQQ)
    monkeypatch.setattr("app.services.email_sync_service.QQIMAPConnector", FakeQQ)

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="mailbox-sync@example.com")
        mailbox = client.post(
            "/api/v1/mailboxes/qq/connect",
            json={"email_address": "tester@qq.com", "auth_code": "secret-code-123"},
        ).json()["data"]

        first = client.post(f"/api/v1/mailboxes/{mailbox['id']}/sync")
        assert first.status_code == 200, first.text
        run = first.json()["data"]
        assert run["status"] == "success"
        assert run["candidate_count"] == 1
        assert run["duplicate_count"] == 0

        second = client.post(f"/api/v1/mailboxes/{mailbox['id']}/sync").json()["data"]
        assert second["candidate_count"] == 0
        assert second["duplicate_count"] >= 1

        candidates = client.get("/api/v1/recruitment-email-candidates").json()["data"]
        assert len(candidates) == 1
        assert candidates[0]["parsed_status"] == "interview"
        assert candidates[0]["review_status"] in {"pending", "conflict"}

    rows = list(db_session.scalars(select(RecruitmentEventCandidate)))
    assert len(rows) == 1


def test_candidate_creates_application_event_on_confirm(
    app: FastAPI, settings: Settings, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.models.enums import JobSourceMethod, VerificationStatus
    from app.db.models.job import Company, Job, JobSource

    _enable_secret(settings, monkeypatch)

    company = Company(name="测试科技", normalized_name="测试科技")
    source = JobSource(source_type="test", source_key="m51", config_json={}, enabled=True)
    db_session.add_all([company, source])
    db_session.flush()
    job = Job(
        source_id=source.id,
        source_job_id="m51-job",
        company_id=company.id,
        title="大模型算法实习生",
        source_url="https://example.com/job",
        content_hash="m51-hash",
        source_method=JobSourceMethod.PUBLIC_PAGE,
        verification_status=VerificationStatus.VERIFIED,
        is_demo=False,
    )
    db_session.add(job)
    db_session.commit()

    message = MailboxMessage(
        provider="qq_imap",
        provider_message_id="msg-2",
        subject="面试邀请",
        sender="hr@testcorp.com",
        received_at=datetime.now(UTC),
        raw=EML,
    )

    class FakeQQ:
        def __init__(self, _settings: Settings) -> None:
            pass

        def test_connection(self, email, code) -> None:
            return None

        def list_messages(self, *args, **kwargs):
            return [message], {}

    monkeypatch.setattr("app.api.v1.mailboxes.QQIMAPConnector", FakeQQ)
    monkeypatch.setattr("app.services.email_sync_service.QQIMAPConnector", FakeQQ)

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="mailbox-confirm@example.com")
        application = client.post(
            "/api/v1/applications", json={"job_id": str(job.id), "status": "applied"}
        ).json()["data"]
        mailbox = client.post(
            "/api/v1/mailboxes/qq/connect",
            json={"email_address": "tester@qq.com", "auth_code": "secret-code-123"},
        ).json()["data"]
        client.post(f"/api/v1/mailboxes/{mailbox['id']}/sync")
        candidate = client.get("/api/v1/recruitment-email-candidates").json()["data"][0]

        confirmed = client.post(
            f"/api/v1/recruitment-email-candidates/{candidate['id']}/confirm",
            json={
                "application_id": application["id"],
                "status": "interview",
                "event_time": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["data"]["review_status"] == "confirmed"

        detail = client.get(f"/api/v1/applications/{application['id']}").json()["data"]
        assert detail["status"] == "interview"
        assert len(detail["events"]) >= 2


def test_gmail_authorize_reports_not_configured(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="mailbox-gmail@example.com")
        response = client.get("/api/v1/mailboxes/gmail/authorize")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["configured"] is False
        assert data["authorize_url"] is None


def test_mailbox_is_user_scoped(
    app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_secret(settings, monkeypatch)

    class FakeQQ:
        def __init__(self, _settings: Settings) -> None:
            pass

        def test_connection(self, email, code) -> None:
            return None

    monkeypatch.setattr("app.api.v1.mailboxes.QQIMAPConnector", FakeQQ)
    with AutoCsrfTestClient(app, settings) as client_a:
        register_user(client_a, email="mailbox-a@example.com")
        mailbox = client_a.post(
            "/api/v1/mailboxes/qq/connect",
            json={"email_address": "a@qq.com", "auth_code": "secret-code-123"},
        ).json()["data"]

        client_b = AutoCsrfTestClient(app, settings)
        register_user(client_b, email="mailbox-b@example.com")
        assert client_b.get("/api/v1/mailboxes").json()["data"] == []
        assert client_b.post(f"/api/v1/mailboxes/{mailbox['id']}/sync").status_code == 404


def test_stale_running_sync_run_is_closed(db_session: Session, settings: Settings) -> None:
    """A worker restart leaves runs in `running`; the page then says "同步中" forever."""
    from app.db.models.mailbox import MailboxConnection, MailboxSyncRun
    from app.db.models.user import User
    from app.services.email_sync_service import EmailSyncService

    user = User(email="stale-run@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    connection = MailboxConnection(
        user_id=user.id,
        provider="gmail",
        email_address="stale-run@example.com",
        status="active",
        sync_enabled=True,
    )
    db_session.add(connection)
    db_session.flush()
    stale = MailboxSyncRun(
        connection_id=connection.id,
        started_at=datetime.now(UTC) - timedelta(minutes=30),
        status="running",
    )
    db_session.add(stale)
    db_session.commit()

    closed = EmailSyncService(db_session, settings).reconcile_stale_runs()

    assert closed == 1
    db_session.refresh(stale)
    assert stale.status == "failed"
    assert stale.finished_at is not None
    assert "任务中断" in (stale.error_summary or "")
