from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.application import ApplicationEvent
from tests.factories import create_job, register_user


def _create_application(client: TestClient, job_id: str) -> dict:
    response = client.post("/api/v1/applications", json={"job_id": job_id, "notes": "用户手动记录"})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_create_application_writes_initial_event(client: TestClient, db_session: Session) -> None:
    register_user(client)
    job = create_job(db_session)

    data = _create_application(client, str(job.id))

    assert data["status"] == "to_apply"
    assert data["source_of_truth"] == "user_manual"
    assert data["job"]["id"] == str(job.id)

    detail = client.get(f"/api/v1/applications/{data['id']}").json()["data"]
    assert len(detail["events"]) == 1
    event = detail["events"][0]
    assert event["from_status"] is None
    assert event["to_status"] == "to_apply"
    assert event["actor"] == "user"
    assert event["evidence_type"] == "manual"


def test_duplicate_application_returns_409(client: TestClient, db_session: Session) -> None:
    register_user(client)
    job = create_job(db_session)
    data = _create_application(client, str(job.id))

    duplicate = client.post("/api/v1/applications", json={"job_id": str(job.id)})

    assert duplicate.status_code == 409
    error = duplicate.json()["error"]
    assert error["code"] == "APPLICATION_EXISTS"
    assert error["details"]["application_id"] == data["id"]


def test_status_update_appends_event_in_one_transaction(
    client: TestClient, db_session: Session
) -> None:
    register_user(client)
    job = create_job(db_session)
    application = _create_application(client, str(job.id))

    update = client.patch(
        f"/api/v1/applications/{application['id']}/status",
        json={"status": "interview", "note": "收到面试邀请"},
    )

    assert update.status_code == 200
    assert update.json()["data"]["status"] == "interview"

    detail = client.get(f"/api/v1/applications/{application['id']}").json()["data"]
    assert [event["to_status"] for event in detail["events"]] == ["to_apply", "interview"]
    assert detail["events"][1]["from_status"] == "to_apply"
    assert detail["events"][1]["note"] == "收到面试邀请"

    events = client.get(f"/api/v1/applications/{application['id']}/events").json()["data"]
    assert len(events) == 2
    assert events[0]["created_at"] <= events[1]["created_at"]


def test_unchanged_status_is_rejected_without_new_event(
    client: TestClient, db_session: Session
) -> None:
    register_user(client)
    job = create_job(db_session)
    application = _create_application(client, str(job.id))

    response = client.patch(
        f"/api/v1/applications/{application['id']}/status",
        json={"status": "to_apply"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPLICATION_STATUS_UNCHANGED"
    assert db_session.scalar(select(func.count(ApplicationEvent.id))) == 1


def test_marking_applied_sets_applied_at(client: TestClient, db_session: Session) -> None:
    register_user(client)
    job = create_job(db_session)
    application = _create_application(client, str(job.id))

    response = client.patch(
        f"/api/v1/applications/{application['id']}/status",
        json={"status": "applied", "note": "我已在官网提交"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["applied_at"] is not None


def test_application_list_filter_and_delete(client: TestClient, db_session: Session) -> None:
    register_user(client)
    first_job = create_job(db_session, source_job_id="app-1")
    second_job = create_job(db_session, source_job_id="app-2")
    first = _create_application(client, str(first_job.id))
    _create_application(client, str(second_job.id))
    client.patch(f"/api/v1/applications/{first['id']}/status", json={"status": "preparing"})

    filtered = client.get("/api/v1/applications", params={"status": "preparing"}).json()
    assert filtered["meta"]["total"] == 1
    assert filtered["data"][0]["id"] == first["id"]

    deleted = client.delete(f"/api/v1/applications/{first['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/applications/{first['id']}").status_code == 404
    assert (
        db_session.scalar(
            select(func.count(ApplicationEvent.id)).where(
                ApplicationEvent.application_id == first["id"]
            )
        )
        == 0
    )


def test_application_requires_existing_visible_job(client: TestClient) -> None:
    register_user(client)

    response = client.post(
        "/api/v1/applications",
        json={"job_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_applications_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/applications").status_code == 401
    assert (
        client.post(
            "/api/v1/applications",
            json={"job_id": "00000000-0000-0000-0000-000000000000"},
        ).status_code
        == 401
    )
