from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import Settings
from app.db.models.profile import CandidateProfile
from tests.conftest import AutoCsrfTestClient, _build_app
from tests.factories import register_user
from tests.test_resume_api import _pdf_bytes
from tests.test_resume_parser import RESUME_TEXT


@pytest.fixture
def profile_app(
    settings: Settings,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> FastAPI:
    monkeypatch.setattr(settings, "file_storage_dir", tmp_path)
    return _build_app(settings, session_factory)


def test_confirm_profile_records_confirmed_at_and_bumps_version(
    profile_app: FastAPI,
    settings: Settings,
) -> None:
    with AutoCsrfTestClient(profile_app, settings) as client:
        register_user(client, email="confirm@example.com")
        client.patch("/api/v1/profile/me", json={"skills": ["Python", "PyTorch"]})
        before = client.get("/api/v1/profile/me").json()["data"]
        assert before["version"] == 1
        assert before["verified_by_user"] is False

        confirmed = client.post("/api/v1/profile/confirm")
        assert confirmed.status_code == 200
        data = confirmed.json()["data"]
        assert data["verified_by_user"] is True
        assert data["confirmed_at"] is not None
        assert data["version"] == 2


def test_apply_resume_populates_profile_but_unconfirmed(
    profile_app: FastAPI,
    settings: Settings,
) -> None:
    with AutoCsrfTestClient(profile_app, settings) as client:
        register_user(client, email="apply@example.com")
        resume = client.post(
            "/api/v1/resumes",
            files={"file": ("a.pdf", _pdf_bytes(RESUME_TEXT), "application/pdf")},
        ).json()["data"]

        applied = client.post(
            "/api/v1/profile/apply-resume",
            json={"resume_id": resume["id"]},
        )
        assert applied.status_code == 200, applied.text
        data = applied.json()["data"]
        assert "pytorch" in data["skills"]
        assert data["education"]
        assert data["education"][0]["school"] == "北京大学"
        assert data["experiences"]
        # The resume has a 项目经历 section: it must land in the projects panel,
        # not inside 实习与项目经历.
        assert data["projects"]
        assert data["projects"][0]["title"] == "基于Transformer的文本分类"
        # The field exists even when the resume gives no period: the user fills
        # it in by hand instead of the value being invented.
        assert data["projects"][0]["time_range"] is None
        assert data["verified_by_user"] is False
        assert data["confirmed_at"] is None


def test_profile_update_and_confirm_populate_content_hash(
    profile_app: FastAPI,
    settings: Settings,
    db_session,
) -> None:
    with AutoCsrfTestClient(profile_app, settings) as client:
        register_user(client, email="hash@example.com")
        client.patch("/api/v1/profile/me", json={"skills": ["Python"]})
        client.post("/api/v1/profile/confirm")

    profile = db_session.scalar(select(CandidateProfile))
    assert profile is not None
    assert profile.content_hash is not None
    assert profile.confirmed_at is not None
    assert profile.verified_by_user is True


def test_cross_user_profile_isolation(
    profile_app: FastAPI,
    settings: Settings,
) -> None:
    with AutoCsrfTestClient(profile_app, settings) as client_a:
        register_user(client_a, email="profile-a@example.com")
        client_a.patch("/api/v1/profile/me", json={"skills": ["Python"]})

        client_b = AutoCsrfTestClient(profile_app, settings)
        register_user(client_b, email="profile-b@example.com")
        assert client_b.get("/api/v1/profile/me").json()["data"]["skills"] == []
