from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.enums import (
    JobSourceMethod,
    JobStatus,
    LeadVerificationStatus,
)
from app.db.models.job import Company
from app.db.models.job_lead import JobLead
from app.db.models.user import User
from app.services.job_lead_service import JobLeadService

JD = "职位描述\n" + "负责大模型 Agent 的算法研发与评测体系建设，参与线上效果优化。" * 20


def _lead(session: Session, url: str, email: str) -> tuple[JobLead, User]:
    user = User(email=email, password_hash="x")
    session.add(user)
    session.flush()
    company = Company(name="阿里巴巴", normalized_name=f"阿里巴巴-{email}")
    session.add(company)
    session.flush()
    lead = JobLead(
        owner_user_id=user.id,
        company_id=company.id,
        title="AI Agent算法工程师（大模型方向）",
        official_url=url,
        source_method=JobSourceMethod.MANUAL_IMPORT,
        verification_status=LeadVerificationStatus.USER_PROVIDED,
        dedupe_key=f"lead-verify-{email}",
    )
    session.add(lead)
    session.commit()
    return lead, user


def test_manual_alibaba_link_is_verifiable_with_the_browser(
    db_session: Session, settings: Settings, monkeypatch
) -> None:
    """JS-rendered official pages must verify through the local browser.

    Tavily's static extraction only sees the shell and reported "JD incomplete",
    which made every manually imported Alibaba posting unverifiable.
    """
    from app.connectors.rendered_page import PageSnapshot

    url = "https://campus-talent.alibaba.com/campus/position/199903900038"
    lead, user = _lead(db_session, url, "verify-rendered@example.com")

    monkeypatch.setattr(
        "app.connectors.rendered_page.RenderedPageReader.available",
        lambda self: (True, ""),
    )
    monkeypatch.setattr(
        "app.connectors.rendered_page.RenderedPageReader.read",
        lambda self, target: PageSnapshot(
            url=target,
            final_url=target,
            title="AI Agent算法工程师（大模型方向）",
            description=JD,
            city="杭州",
            job_type="campus",
            status=JobStatus.OPEN,
            status_evidence="读到官方详情正文",
        ),
    )

    updated, _outcome = JobLeadService(db_session, settings).verify(lead.id, user.id)

    assert updated.verification_status == LeadVerificationStatus.VERIFIED_OFFICIAL
    assert updated.job_id is not None
    assert updated.last_verification_error is None


def test_unreadable_page_still_falls_back_to_extraction(
    db_session: Session, settings: Settings, monkeypatch
) -> None:
    """A failed browser read must not be reported as a verification failure."""
    from app.connectors.rendered_page import PageSnapshot

    url = "https://campus-talent.alibaba.com/campus/position/199903900039"
    lead, _user = _lead(db_session, url, "verify-fallback@example.com")

    monkeypatch.setattr(
        "app.connectors.rendered_page.RenderedPageReader.available",
        lambda self: (True, ""),
    )
    monkeypatch.setattr(
        "app.connectors.rendered_page.RenderedPageReader.read",
        lambda self, target: PageSnapshot(
            url=target,
            final_url=target,
            title="岗位列表",
            description="",
            status=JobStatus.UNKNOWN,
        ),
    )

    service = JobLeadService(db_session, settings)
    # The rendered path declines; the caller then uses Tavily extraction, which
    # has no key in tests and surfaces as a readable error instead.
    assert service._verify_with_rendered_page(lead, type("O", (), {"company": "alibaba"})()) is None


def test_verify_many_reports_each_lead_independently(
    db_session: Session, settings: Settings, monkeypatch
) -> None:
    """One bad lead must not abort the batch."""
    from types import SimpleNamespace

    from app.core.errors import AppError

    first, user = _lead(
        db_session, "https://campus-talent.alibaba.com/campus/position/1", "batch-a@example.com"
    )
    second, _ = _lead(
        db_session, "https://campus-talent.alibaba.com/campus/position/2", "batch-b@example.com"
    )

    def fake_verify(self, lead_id, user_id):
        if lead_id == first.id:
            return SimpleNamespace(title="核验成功岗位"), None
        raise AppError("INVALID_SOURCE_URL", "该链接不是可信职位详情页", status_code=422)

    monkeypatch.setattr(JobLeadService, "_verify_lead", fake_verify)
    monkeypatch.setattr(JobLeadService, "_check_verify_rate_limit", lambda self, uid, cost=1: None)

    result = JobLeadService(db_session, settings).verify_many(
        [first.id, second.id], user.id, limit=10
    )

    assert result["requested"] == 2
    assert result["verified"] == 1
    assert result["failed"] == 1
    statuses = {item["lead_id"]: item["status"] for item in result["results"]}
    assert statuses[str(first.id)] == "verified"
    assert statuses[str(second.id)] == "failed"
    failure = next(item for item in result["results"] if item["status"] == "failed")
    assert "INVALID_SOURCE_URL" in (failure["error"] or "")


def test_verify_many_requires_at_least_one_lead(
    db_session: Session, settings: Settings, monkeypatch
) -> None:
    from app.core.errors import AppError

    monkeypatch.setattr(JobLeadService, "_check_verify_rate_limit", lambda self, uid, cost=1: None)

    try:
        JobLeadService(db_session, settings).verify_many([], "00000000-0000-0000-0000-000000000000")
    except AppError as exc:
        assert exc.code == "NO_LEADS_SELECTED"
    else:  # pragma: no cover
        raise AssertionError("expected NO_LEADS_SELECTED")
