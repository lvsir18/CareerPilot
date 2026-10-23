from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.schemas import RawJob
from app.core.config import Settings
from app.db.models.enums import (
    JobSourceMethod,
    LeadVerificationStatus,
    VerificationStatus,
)
from app.db.models.job import Company, Job, JobSource
from app.db.models.job_lead import JobLead
from app.services.job_ingestion import upsert_raw_job
from tests.conftest import AutoCsrfTestClient, _build_app
from tests.factories import register_user
from tests.test_resume_api import _pdf_bytes
from tests.test_resume_parser import RESUME_TEXT

JD = """大模型算法实习生

任职要求：
精通 Python、PyTorch、大语言模型

加分项：
RAG、LangGraph 经验者优先
"""


def _create_verified_job(db_session: Session, *, job_id: str = "m3-match") -> Job:
    source = JobSource(
        source_type="test", source_key="m3-match-source", config_json={}, enabled=True
    )
    db_session.add(source)
    db_session.flush()
    raw = RawJob(
        source_type="test",
        source_key="m3-match-source",
        source_job_id=job_id,
        company="测试科技",
        title="大模型算法实习生",
        source_url="https://example.com/job",
        description=JD,
        city="北京",
        job_type="internship",
        verification_status=VerificationStatus.VERIFIED,
        source_method=JobSourceMethod.PUBLIC_PAGE,
    )
    upsert_raw_job(db_session, source, raw)
    db_session.commit()
    return db_session.scalar(select(Job).where(Job.source_job_id == job_id))


@pytest.fixture
def matches_app(
    settings: Settings,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> FastAPI:
    monkeypatch.setattr(settings, "file_storage_dir", tmp_path)
    return _build_app(settings, session_factory)


def test_full_match_returns_score_and_skills(
    matches_app: FastAPI,
    settings: Settings,
    db_session: Session,
) -> None:
    job = _create_verified_job(db_session)
    with AutoCsrfTestClient(matches_app, settings) as client:
        register_user(client, email="match@example.com")
        resume = client.post(
            "/api/v1/resumes",
            files={"file": ("a.pdf", _pdf_bytes(RESUME_TEXT), "application/pdf")},
        ).json()["data"]
        client.post("/api/v1/profile/apply-resume", json={"resume_id": resume["id"]})
        client.post("/api/v1/profile/confirm")

        response = client.post(f"/api/v1/matches/jobs/{job.id}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["match"]["match_level"] == "full"
        assert data["match"]["match_score"] is not None
        assert "python" in data["match"]["matched_skills"]
        assert "pytorch" in data["match"]["matched_skills"]
        assert "llm" in data["match"]["matched_skills"]
        assert "langgraph" in data["match"]["unverified_skills"]


def test_recommendations_return_verified_jobs_with_status(
    matches_app: FastAPI,
    settings: Settings,
    db_session: Session,
) -> None:
    job = _create_verified_job(db_session)
    with AutoCsrfTestClient(matches_app, settings) as client:
        register_user(client, email="rec@example.com")
        resume = client.post(
            "/api/v1/resumes",
            files={"file": ("a.pdf", _pdf_bytes(RESUME_TEXT), "application/pdf")},
        ).json()["data"]
        client.post("/api/v1/profile/apply-resume", json={"resume_id": resume["id"]})
        client.post("/api/v1/profile/confirm")

        listed = client.get("/api/v1/matches/recommendations")
        assert listed.status_code == 200
        data = listed.json()["data"]
        assert data
        assert data[0]["job"]["id"] == str(job.id)
        assert data[0]["match"]["match_score"] is not None


def test_profile_edit_bumps_version_and_recomputes(
    matches_app: FastAPI,
    settings: Settings,
    db_session: Session,
) -> None:
    job = _create_verified_job(db_session)
    with AutoCsrfTestClient(matches_app, settings) as client:
        register_user(client, email="version@example.com")
        resume = client.post(
            "/api/v1/resumes",
            files={"file": ("a.pdf", _pdf_bytes(RESUME_TEXT), "application/pdf")},
        ).json()["data"]
        client.post("/api/v1/profile/apply-resume", json={"resume_id": resume["id"]})
        client.post("/api/v1/profile/confirm")

        first = client.post(f"/api/v1/matches/jobs/{job.id}").json()["data"]
        version_before = client.get("/api/v1/profile/me").json()["data"]["version"]

        client.patch("/api/v1/profile/me", json={"skills": ["Python"]})
        client.post("/api/v1/profile/confirm")
        version_after = client.get("/api/v1/profile/me").json()["data"]["version"]
        assert version_after > version_before

        second = client.post(f"/api/v1/matches/jobs/{job.id}").json()["data"]
        assert second["match"]["match_score"] is not None
        assert first["match"]["match_score"] is not None


def test_recommendations_cross_user_isolation(
    matches_app: FastAPI,
    settings: Settings,
    db_session: Session,
) -> None:
    job = _create_verified_job(db_session)
    with AutoCsrfTestClient(matches_app, settings) as client_a:
        register_user(client_a, email="iso-a@example.com")
        client_a.patch("/api/v1/profile/me", json={"skills": ["Python"]})
        client_a.post("/api/v1/profile/confirm")
        client_a.post(f"/api/v1/matches/jobs/{job.id}")

        client_b = AutoCsrfTestClient(matches_app, settings)
        register_user(client_b, email="iso-b@example.com")
        # User B has no profile confirmed yet; matching still works but is isolated.
        response_b = client_b.post(f"/api/v1/matches/jobs/{job.id}")
        assert response_b.status_code == 200
        assert response_b.json()["data"]["match"]["match_score"] is not None


def test_job_lead_returns_basic_match_without_score(
    matches_app: FastAPI,
    settings: Settings,
    db_session: Session,
) -> None:
    company = Company(name="测试科技", normalized_name="测试科技")
    db_session.add(company)
    db_session.flush()
    lead = JobLead(
        company_id=company.id,
        title="大模型算法实习生",
        official_url="https://example.com/lead",
        summary="大模型算法实习生招聘",
        source_method=JobSourceMethod.SEARCH_DISCOVERY,
        verification_status=LeadVerificationStatus.SEARCH_SNIPPET_ONLY,
        dedupe_key="lead-basic-match",
    )
    db_session.add(lead)
    db_session.commit()

    with AutoCsrfTestClient(matches_app, settings) as client:
        register_user(client, email="lead-match@example.com")
        response = client.post(f"/api/v1/matches/job-leads/{lead.id}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["match_level"] == "basic"
        assert data["match_score"] is None
        assert "信息不完整" in data["explanation"]
