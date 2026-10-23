from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.baidu import parse_detail_html
from app.core.config import Settings
from app.db.models.job import Job
from app.db.models.job_lead import JobLead, SourceEvidence
from tests.conftest import AutoCsrfTestClient, _build_app
from tests.factories import register_user

BAIDU_URL = "https://talent.baidu.com/jobs/detail/INTERN/f8f8f186-2d4a-4b55-9f6c-34018f476896"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "baidu_detail.html"


def _fake_connector() -> object:
    class Fake:
        def fetch_job_detail(self, url: str):
            return parse_detail_html(FIXTURE.read_text(encoding="utf-8"), requested_url=url)

        def close(self) -> None:
            pass

    return Fake()


def test_private_lead_is_user_scoped(app: FastAPI, settings: Settings, db_session: Session) -> None:
    with AutoCsrfTestClient(app, settings) as user_a:
        register_user(user_a, email="lead-a@example.com")
        imported = user_a.post(
            "/api/v1/job-leads/import",
            json={
                "url": BAIDU_URL,
                "title": "用户看到的 Agent 实习",
                "description": "用户手工粘贴的 JD",
                "city": "北京",
            },
        )
        assert imported.status_code == 201
        lead_id = imported.json()["data"]["id"]
        assert imported.json()["data"]["is_private"] is True
        assert imported.json()["data"]["verification_status"] == "user_provided"

    with AutoCsrfTestClient(app, settings) as user_b:
        register_user(user_b, email="lead-b@example.com")
        assert user_b.get(f"/api/v1/job-leads/{lead_id}").status_code == 404
        assert user_b.get("/api/v1/job-leads").json()["data"] == []

    with AutoCsrfTestClient(app, settings) as user_a:
        user_a.post(
            "/api/v1/auth/login",
            json={"email": "lead-a@example.com", "password": "strong-pass-123"},
        )
        assert len(user_a.get("/api/v1/job-leads").json()["data"]) == 1


def test_verify_lead_creates_verified_job_and_evidence(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.job_lead_service.BaiduPublicConnector",
        lambda _settings: _fake_connector(),
    )
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="verify@example.com")
        imported = client.post(
            "/api/v1/job-leads/import",
            json={"url": BAIDU_URL, "title": "待核验 Agent 实习"},
        )
        lead_id = imported.json()["data"]["id"]

        verified = client.post(f"/api/v1/job-leads/{lead_id}/verify")
        assert verified.status_code == 200
        data = verified.json()["data"]
        assert data["lead"]["verification_status"] == "verified_official"
        assert data["lead"]["job_id"] == data["job_id"]
        assert data["created"] is True

        job = db_session.scalar(select(Job))
        assert job is not None
        assert job.is_demo is False
        assert job.source_method == "public_page"
        assert job.verification_status == "verified"

        detail = client.get(f"/api/v1/jobs/{job.id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["evidence"]

        again = client.post(f"/api/v1/job-leads/{lead_id}/verify")
        assert again.status_code == 409

    evidence = list(db_session.scalars(select(SourceEvidence)))
    assert evidence
    assert any(item.evidence_kind == "official_page" for item in evidence)
    lead = db_session.scalar(select(JobLead))
    assert lead is not None and lead.verification_status == "verified_official"


def test_discovery_without_search_provider_returns_existing_data(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    discovery_settings = settings.model_copy(
        update={
            "search_provider": "none",
            "official_site_discovery_enabled": False,
        }
    )
    app = _build_app(discovery_settings, session_factory)
    with AutoCsrfTestClient(app, discovery_settings) as client:
        register_user(client, email="discover-none@example.com")
        response = client.get("/api/v1/jobs/discover", params={"query": "Agent"})

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["search"]["configured"] is False
    assert body["search"]["licensed_configured"] is False
    assert any("未配置" in warning for warning in body["search"]["warnings"])
    assert body["leads"] == []


MINIMAX_URL = "https://vrfi1sk8a0.jobs.feishu.cn/379481/position/7655253685333936403/detail"
MINIMAX_JD = """# 大模型算法实习生

工作地点：北京

职位描述
1. 参与大模型 Agent 的算法研发和评测。
2. 与产品和工程团队协作推进落地。

任职要求
1. 熟悉 Python、PyTorch 和大模型基础。
2. 有 RAG 或 Agent 项目经验优先。
3. 具备良好的工程能力、沟通能力和团队协作意识，能够持续跟进业务与模型的迭代。
4. 对招聘流程、候选人体验和内容质量有责任心，能在快节奏环境中稳定交付。
"""


def test_verify_ats_lead_with_tavily_extract_creates_verified_job(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.tavily_extract import ExtractedPage

    class FakeExtractor:
        def __init__(self, _settings: Settings) -> None:
            pass

        def extract(self, url: str, *, user_id=None) -> ExtractedPage:
            return ExtractedPage(url=url, success=True, content=MINIMAX_JD, credits_estimated=1)

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "app.services.job_lead_service.TavilyExtractService",
        FakeExtractor,
    )
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="verify-ats@example.com")
        imported = client.post(
            "/api/v1/job-leads/import",
            json={"url": MINIMAX_URL, "title": "大模型算法实习生"},
        )
        assert imported.status_code == 201
        lead_id = imported.json()["data"]["id"]

        verified = client.post(f"/api/v1/job-leads/{lead_id}/verify")
        assert verified.status_code == 200, verified.text
        data = verified.json()["data"]
        assert data["lead"]["verification_status"] == "verified_official"
        assert data["lead"]["last_verification_error"] is None

        job = db_session.scalar(select(Job))
        assert job is not None
        assert job.source.source_type == "tavily_extract"
        assert job.verification_status == "verified"
        assert job.title == "大模型算法实习生"
        assert job.department is None

        detail = client.get(f"/api/v1/jobs/{job.id}")
        assert detail.status_code == 200
        detail_data = detail.json()["data"]
        assert detail_data["source_type"] == "tavily_extract"
        assert detail_data["skills"] == []
        assert detail_data["official_job_id"] == "7655253685333936403"

    evidence = list(db_session.scalars(select(SourceEvidence)))
    assert any(item.verification_method == "tavily_extract" for item in evidence)


def test_incomplete_extracted_jd_does_not_upgrade_lead(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.tavily_extract import ExtractedPage

    class FakeExtractor:
        def __init__(self, _settings: Settings) -> None:
            pass

        def extract(self, url: str, *, user_id=None) -> ExtractedPage:
            return ExtractedPage(url=url, success=True, content="首页 登录", credits_estimated=1)

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "app.services.job_lead_service.TavilyExtractService",
        FakeExtractor,
    )
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="verify-incomplete@example.com")
        imported = client.post(
            "/api/v1/job-leads/import",
            json={"url": MINIMAX_URL, "title": "大模型算法实习生"},
        )
        lead_id = imported.json()["data"]["id"]
        response = client.post(f"/api/v1/job-leads/{lead_id}/verify")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "JD_INCOMPLETE"
        row = db_session.get(JobLead, lead_id)
        assert row is not None
        assert row.verification_status != "verified_official"
        assert row.last_verification_error
        assert db_session.scalar(select(Job)) is None
