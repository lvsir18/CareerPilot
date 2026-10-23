from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.application import Application
from app.db.models.saved_job import SavedJob
from app.db.models.user import User
from tests.conftest import AutoCsrfTestClient
from tests.factories import create_job, register_user


def test_users_cannot_read_or_modify_each_others_data(
    app: FastAPI, client: TestClient, db_session: Session, settings
) -> None:
    register_user(client, email="user-a@example.com")
    user_a = db_session.scalar(select(User).where(User.email == "user-a@example.com"))
    assert user_a is not None

    profile = client.patch(
        "/api/v1/profile/me",
        json={"headline": "A 的画像", "skills": ["Python"]},
    )
    assert profile.status_code == 200

    job = create_job(db_session, source_job_id="isolation-job", title="隔离测试岗位")
    saved = client.post(f"/api/v1/jobs/{job.id}/save", json={"list_type": "saved"})
    assert saved.status_code == 201
    application = client.post("/api/v1/applications", json={"job_id": str(job.id)})
    assert application.status_code == 201
    application_id = application.json()["data"]["id"]

    with AutoCsrfTestClient(app, settings) as user_b:
        register_user(user_b, email="user-b@example.com")
        user_b_profile = user_b.get("/api/v1/profile/me").json()["data"]
        assert user_b_profile["headline"] is None
        assert user_b_profile["skills"] == []

        assert user_b.get("/api/v1/saved-jobs").json()["meta"]["total"] == 0
        assert user_b.get("/api/v1/applications").json()["meta"]["total"] == 0

        assert user_b.get(f"/api/v1/applications/{application_id}").status_code == 404
        assert (
            user_b.patch(
                f"/api/v1/applications/{application_id}/status",
                json={"status": "interview"},
            ).status_code
            == 404
        )
        assert user_b.get(f"/api/v1/applications/{application_id}/events").status_code == 404
        assert user_b.delete(f"/api/v1/applications/{application_id}").status_code == 404

        # B can independently save the same public job.
        own_save = user_b.post(f"/api/v1/jobs/{job.id}/save", json={"list_type": "saved"})
        assert own_save.status_code == 201

    assert client.get("/api/v1/saved-jobs").json()["meta"]["total"] == 1
    assert client.get("/api/v1/applications").json()["meta"]["total"] == 1
    assert client.get("/api/v1/profile/me").json()["data"]["headline"] == "A 的画像"

    assert db_session.scalar(select(func.count(SavedJob.id))) == 2
    assert db_session.scalar(select(func.count(Application.id))) == 1
