from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.saved_job import SavedJob
from tests.factories import create_job, register_user


def test_save_is_idempotent_and_supports_both_lists(
    client: TestClient, db_session: Session
) -> None:
    register_user(client)
    job = create_job(db_session)

    first = client.post(f"/api/v1/jobs/{job.id}/save", json={"list_type": "saved", "note": "关注"})
    duplicate = client.post(
        f"/api/v1/jobs/{job.id}/save", json={"list_type": "saved", "note": "关注"}
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert first.json()["data"]["id"] == duplicate.json()["data"]["id"]
    count = db_session.scalar(select(func.count(SavedJob.id)))
    assert count == 1

    to_apply = client.post(f"/api/v1/jobs/{job.id}/save", json={"list_type": "to_apply"})
    assert to_apply.status_code == 201

    saved_list = client.get("/api/v1/saved-jobs", params={"list_type": "saved"}).json()
    assert saved_list["meta"]["total"] == 1
    assert saved_list["data"][0]["job"]["id"] == str(job.id)

    all_lists = client.get("/api/v1/saved-jobs").json()
    assert all_lists["meta"]["total"] == 2


def test_unsave_is_idempotent(client: TestClient, db_session: Session) -> None:
    register_user(client)
    job = create_job(db_session)
    client.post(f"/api/v1/jobs/{job.id}/save", json={})

    first = client.delete(f"/api/v1/jobs/{job.id}/save", params={"list_type": "saved"})
    second = client.delete(f"/api/v1/jobs/{job.id}/save", params={"list_type": "saved"})

    assert first.status_code == 204
    assert second.status_code == 204
    assert client.get("/api/v1/saved-jobs").json()["meta"]["total"] == 0


def test_save_unknown_job_returns_404(client: TestClient) -> None:
    register_user(client)

    response = client.post("/api/v1/jobs/00000000-0000-0000-0000-000000000000/save", json={})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_saved_jobs_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/saved-jobs").status_code == 401
