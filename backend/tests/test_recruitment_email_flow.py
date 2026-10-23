"""Recruitment email fixture matrix (isolated, no real mailbox involved).

Covers parse → filter → application matching → conflict classification, and one
API-level confirm that writes a real ApplicationEvent.

These are FIXTURE tests. They do not prove a real QQ/Gmail mailbox delivered a
real recruiting notification.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.application import Application, ApplicationEvent
from app.db.models.enums import (
    ApplicationSourceType,
    ApplicationStatus,
    JobSourceMethod,
    VerificationStatus,
)
from app.db.models.job import Company, Job, JobSource
from app.db.models.mailbox import RecruitmentEventCandidate
from app.services.email_parser import parse_eml
from app.services.email_sync_service import ConflictDetectionService, RecruitmentEmailFilter
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user


def eml(
    *,
    subject: str,
    body: str,
    sender: str = "招聘组 <hr@bytedance.com>",
    date: str = "Wed, 21 Oct 2026 10:00:00 +0800",
) -> bytes:
    return (
        f"From: {sender}\n"
        "To: user@example.com\n"
        f"Subject: {subject}\n"
        f"Date: {date}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        f"{body}\n"
    ).encode()


# (name, eml, expect_recruitment, expect_status, expect_company)
CASES = [
    (
        "applied_ack",
        eml(
            subject="申请已收到 - 大模型算法实习生",
            body="您好，我们已收到您的申请，将尽快安排简历筛选。",
        ),
        True,
        "applied",
        "字节跳动",
    ),
    (
        "assessment_invite",
        eml(
            subject="笔试邀请 - 大模型算法实习生",
            body="邀请您参加在线笔试，笔试时间：2026-10-25 14:00。",
        ),
        True,
        "assessment",
        "字节跳动",
    ),
    (
        "interview_invite",
        eml(
            subject="面试邀请 - 大模型算法实习生",
            body="邀请您参加面试，面试时间：2026-10-26 15:30。",
        ),
        True,
        "interview",
        "字节跳动",
    ),
    (
        "interview_reschedule",
        eml(
            subject="面试时间调整通知 - 大模型算法实习生",
            body="原定面试需要调整，新的面试时间：2026-10-28 10:00。",
        ),
        True,
        "interview",
        "字节跳动",
    ),
    (
        "offer_letter",
        eml(
            subject="录用通知 - 大模型算法实习生",
            body="恭喜您被录用，录用通知详见附件，请于一周内回复。",
            sender="HR <hr@meituan.com>",
        ),
        True,
        "offer",
        "美团",
    ),
    (
        "rejection",
        eml(
            subject="感谢您的投递 - 大模型算法实习生",
            body="很遗憾地通知您，本次岗位暂不匹配，流程终止。",
            sender="HR <hr@xiaohongshu.com>",
        ),
        True,
        "rejected",
        "小红书",
    ),
    (
        "unclear",
        eml(
            subject="关于您的求职申请 - 岗位沟通",
            body="感谢关注，我们会在合适的时候与您联系。",
            sender="招聘组 <hr@careers.tencent.com>",
        ),
        True,
        None,
        "腾讯",
    ),
    (
        "marketing_noise",
        eml(
            subject="The new Mac mini just landed",
            body="Special offer for you. Pre-order now.",
            sender="Apple <News@InsideApple.Apple.com>",
        ),
        False,
        None,
        None,
    ),
    (
        "github_ci_noise",
        eml(
            subject="Run failed: CI - main",
            body="Your workflow failed.",
            sender="GitHub <notifications@github.com>",
        ),
        False,
        None,
        None,
    ),
    (
        "unknown_company",
        eml(
            subject="笔试邀请 - 数据分析实习生",
            body="邀请您参加笔试，笔试时间：2026-10-27 09:00。",
            sender="招聘 <hr@unknown-startup.example>",
        ),
        True,
        "assessment",
        None,
    ),
]


@pytest.mark.parametrize(
    ("name", "raw", "expect_recruitment", "expect_status", "expect_company"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_recruitment_email_matrix(
    name: str,
    raw: bytes,
    expect_recruitment: bool,
    expect_status: str | None,
    expect_company: str | None,
) -> None:
    parsed = parse_eml(raw)
    assert RecruitmentEmailFilter.is_recruitment(parsed) is expect_recruitment
    if not expect_recruitment:
        assert parsed.company is None
        return
    assert (parsed.status.value if parsed.status else None) == expect_status
    assert parsed.company == expect_company


def test_interview_time_is_not_email_send_time() -> None:
    """邮件发送时间不能当作面试预约时间。"""
    raw = eml(
        subject="面试邀请 - 大模型算法实习生",
        body="邀请您参加面试，面试时间：2026-10-26 15:30。",
        date="Wed, 21 Oct 2026 10:00:00 +0800",
    )
    parsed = parse_eml(raw)
    assert parsed.received_at is not None
    assert parsed.event_time is not None
    # Parsed appointment time comes from the body, not the Date header.
    assert parsed.event_time.date() != parsed.received_at.date()


def test_conflict_duplicate_out_of_order_and_missing(
    db_session: Session, settings: Settings
) -> None:
    from uuid import uuid4

    from app.db.models.user import User

    user = User(email="conflict-matrix@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()

    company = Company(name="字节跳动", normalized_name="字节跳动")
    source = JobSource(source_type="test", source_key="conflict-src", config_json={}, enabled=True)
    db_session.add_all([company, source])
    db_session.flush()
    job = Job(
        source_id=source.id,
        source_job_id="conflict-job",
        company_id=company.id,
        title="大模型算法实习生",
        source_url="https://example.com/job",
        content_hash="conflict-hash",
        source_method=JobSourceMethod.PUBLIC_PAGE,
        verification_status=VerificationStatus.VERIFIED,
        is_demo=False,
    )
    db_session.add(job)
    db_session.flush()
    application = Application(
        user_id=user.id,
        job_id=job.id,
        status=ApplicationStatus.INTERVIEW,
        dedupe_key="conflict-matrix-application",
    )
    db_session.add(application)
    db_session.flush()
    future = datetime.now(UTC) + timedelta(days=3)
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            from_status=ApplicationStatus.APPLIED,
            to_status=ApplicationStatus.INTERVIEW,
            event_time=future,
            source_type=ApplicationSourceType.EMAIL_IMPORT.value,
            evidence_type="email",
            source_reference=f"seed-{uuid4().hex[:8]}",
            evidence_summary="seed",
            verification_status="email_confirmed",
        )
    )
    db_session.commit()

    service = ConflictDetectionService(db_session, settings)

    interview = parse_eml(
        eml(subject="面试邀请 - 大模型算法实习生", body="面试时间：2026-10-26 15:30。")
    )
    # Same stage + same time as the seeded event → duplicate.
    seeded = dataclasses.replace(interview, event_time=future)
    kind, _ = service.detect(user.id, application.id, seeded)
    assert kind == "duplicate"

    # Older assessment mail must not roll back the current interview state.
    older = parse_eml(
        eml(subject="笔试邀请 - 大模型算法实习生", body="笔试时间：2026-10-10 09:00。")
    )
    kind, reason = service.detect(user.id, application.id, older)
    assert kind == "out_of_order"
    assert reason

    # Mail without a clear stage.
    unclear = parse_eml(
        eml(
            subject="关于您的申请",
            body="感谢关注，我们会尽快联系您。",
            sender="招聘组 <hr@tencent.com>",
        )
    )
    kind, _ = service.detect(user.id, application.id, unclear)
    assert kind == "missing_information"

    # No matched application.
    kind, _ = service.detect(user.id, None, interview)
    assert kind == "ambiguous_match"


def test_confirm_candidate_writes_event_and_is_idempotent(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.mailbox_connectors import MailboxMessage

    message = MailboxMessage(
        provider="qq_imap",
        provider_message_id="fixture-interview-1",
        subject="面试邀请",
        sender="hr@bytedance.com",
        received_at=datetime.now(UTC),
        raw=eml(
            subject="面试邀请 - 大模型算法实习生",
            body="邀请您参加面试，面试时间：2026-11-02 14:00。",
        ),
    )

    class FakeQQ:
        def __init__(self, _settings: Settings) -> None:
            pass

        def test_connection(self, email, code) -> None:
            return None

        def list_messages(self, *args, **kwargs):
            return [message], {"imap_uidvalidity": 7, "imap_last_uid": 7}

    monkeypatch.setattr("app.api.v1.mailboxes.QQIMAPConnector", FakeQQ)
    monkeypatch.setattr("app.services.email_sync_service.QQIMAPConnector", FakeQQ)
    # A real Fernet key is required before credentials can be stored.
    from cryptography.fernet import Fernet

    monkeypatch.setattr(settings, "mailbox_secret_key", Fernet.generate_key().decode())

    company = Company(name="字节跳动", normalized_name="字节跳动")
    source = JobSource(source_type="test", source_key="confirm-src", config_json={}, enabled=True)
    db_session.add_all([company, source])
    db_session.flush()
    job = Job(
        source_id=source.id,
        source_job_id="confirm-job",
        company_id=company.id,
        title="大模型算法实习生",
        source_url="https://example.com/job",
        content_hash="confirm-hash",
        source_method=JobSourceMethod.PUBLIC_PAGE,
        verification_status=VerificationStatus.VERIFIED,
        is_demo=False,
    )
    db_session.add(job)
    db_session.commit()

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="email-flow-a@example.com")
        application = client.post(
            "/api/v1/applications", json={"job_id": str(job.id), "status": "applied"}
        ).json()["data"]
        mailbox = client.post(
            "/api/v1/mailboxes/qq/connect",
            json={"email_address": "flow@qq.com", "auth_code": "code-1234"},
        ).json()["data"]

        client.post(f"/api/v1/mailboxes/{mailbox['id']}/sync")
        candidates = client.get("/api/v1/recruitment-email-candidates").json()["data"]
        assert len(candidates) == 1
        candidate = candidates[0]

        first = client.post(
            f"/api/v1/recruitment-email-candidates/{candidate['id']}/confirm",
            json={"application_id": application["id"], "status": "interview"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["data"]["review_status"] == "confirmed"

        # Confirming again must not create a duplicate application event.
        client.post(
            f"/api/v1/recruitment-email-candidates/{candidate['id']}/confirm",
            json={"application_id": application["id"], "status": "interview"},
        )

    events = list(
        db_session.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application["id"])
            .order_by(ApplicationEvent.created_at)
        )
    )
    interview_events = [e for e in events if e.to_status == ApplicationStatus.INTERVIEW]
    assert len(interview_events) == 1
    assert interview_events[0].source_type == ApplicationSourceType.EMAIL_IMPORT.value

    candidates = list(db_session.scalars(select(RecruitmentEventCandidate)))
    assert len(candidates) == 1
