from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.baidu import BaiduPublicConnector, parse_detail_html
from app.connectors.errors import ConnectorNotConfigured, ConnectorParseError
from app.core.config import Settings
from app.db.models.enums import (
    JobSourceMethod,
    JobStatus,
    VerificationStatus,
)
from app.db.models.job import Job
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "baidu_detail.html"
URL = "https://talent.baidu.com/jobs/detail/INTERN/f8f8f186-2d4a-4b55-9f6c-34018f476896"


def test_baidu_detail_parser_extracts_official_fields() -> None:
    page = FIXTURE.read_text(encoding="utf-8")

    raw = parse_detail_html(page, requested_url=URL)

    assert raw.source_job_id == "f8f8f186-2d4a-4b55-9f6c-34018f476896"
    assert raw.title == "Agent策略工程师（J106592）"
    assert raw.company == "百度"
    assert raw.city == "北京"
    assert raw.location_text == "北京市"
    assert raw.job_type == "internship"
    assert raw.recruitment_program == "日常实习项目"
    assert raw.published_at == datetime(2026, 10, 20, tzinfo=UTC)
    assert raw.requirements == ["-熟悉 Python", "-有 Agent 项目经验"]
    assert raw.status == JobStatus.OPEN
    assert raw.source_method == JobSourceMethod.PUBLIC_PAGE
    assert raw.verification_status == VerificationStatus.VERIFIED
    assert raw.is_demo is False


def test_baidu_parser_rejects_closed_and_unstructured_pages() -> None:
    closed = FIXTURE.read_text(encoding="utf-8").replace('"isValid":true', '"isValid":false')
    with pytest.raises(ConnectorParseError):
        parse_detail_html(closed, requested_url=URL)

    with pytest.raises(ConnectorParseError):
        parse_detail_html("<html>无数据</html>", requested_url=URL)


def test_baidu_url_allowlist() -> None:
    connector = BaiduPublicConnector(Settings(app_env="test"))
    try:
        canonical = connector.validate_url(URL)
        assert canonical == URL
        with pytest.raises(ConnectorNotConfigured):
            connector.validate_url("https://evil.example.com/jobs/detail/INTERN/x")
        with pytest.raises(ConnectorNotConfigured):
            connector.validate_url("http://talent.baidu.com/jobs/list")
    finally:
        connector.close()


class _FakeBaiduConnector:
    def __init__(self) -> None:
        self.raw = parse_detail_html(FIXTURE.read_text(encoding="utf-8"), requested_url=URL)

    def validate_url(self, url: str) -> str:
        if urlsplit(url).hostname != "talent.baidu.com":
            raise ConnectorNotConfigured("仅支持百度")
        return url

    def fetch_job_detail(self, url: str):
        return self.raw

    def close(self) -> None:
        pass


def test_preview_and_import_public_page(
    app: FastAPI,
    settings: Settings,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.job_import_service.BaiduPublicConnector",
        lambda _settings: _FakeBaiduConnector(),
    )

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="importer@example.com")

        preview = client.post("/api/v1/job-imports/preview", json={"url": URL})
        assert preview.status_code == 200
        data = preview.json()["data"]
        assert data["verification_status"] == "verified"
        assert data["source_method"] == "public_page"
        assert data["title"] == "Agent策略工程师（J106592）"
        assert data["verified_at"]
        assert any("UTC 00:00" in item for item in data["warnings"])

        first = client.post(
            "/api/v1/job-imports",
            json={"url": URL, "mode": "public_page", "confirmed": True},
        )
        assert first.status_code == 201
        job_id = first.json()["data"]["id"]
        assert first.json()["data"]["verification_status"] == "verified"
        assert first.json()["data"]["source_method"] == "public_page"
        assert first.json()["data"]["is_demo"] is False

        second = client.post(
            "/api/v1/job-imports",
            json={"url": URL, "mode": "public_page", "confirmed": True},
        )
        assert second.status_code == 201
        assert second.json()["data"]["id"] == job_id

    jobs = list(db_session.scalars(select(Job)))
    assert len(jobs) == 1
    assert jobs[0].source_method == JobSourceMethod.PUBLIC_PAGE
    assert jobs[0].verification_status == VerificationStatus.VERIFIED
    assert jobs[0].source_job_id == "f8f8f186-2d4a-4b55-9f6c-34018f476896"


def test_legacy_manual_paste_points_to_private_leads(
    app: FastAPI,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.job_import_service.BaiduPublicConnector",
        lambda _settings: _FakeBaiduConnector(),
    )
    payload = {
        "url": URL,
        "mode": "manual_paste",
        "confirmed": True,
        "company": "百度",
        "title": "用户粘贴的岗位",
        "description": "用户从官方页面复制的完整 JD",
    }

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="paste@example.com")
        response = client.post("/api/v1/job-imports", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "USE_JOB_LEADS_IMPORT"


def test_import_rejects_untrusted_url(
    app: FastAPI,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.job_import_service.BaiduPublicConnector",
        lambda _settings: _FakeBaiduConnector(),
    )
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="untrusted@example.com")
        response = client.post(
            "/api/v1/job-imports/preview",
            json={
                "url": "https://evil.example.com/jobs/detail/INTERN/f8f8f186-2d4a-4b55-9f6c-34018f476896"
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_IMPORT_URL"
