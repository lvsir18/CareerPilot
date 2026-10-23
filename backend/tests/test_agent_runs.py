from __future__ import annotations

import uuid
from pathlib import Path as _Path

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.agent_run import AgentRun, AgentRunEvent
from tests.conftest import AutoCsrfTestClient, _build_app
from tests.factories import register_user

REQUEST_A = "req-fixed-0001"
REQUEST_B = "req-fixed-0002"


@pytest.fixture
def app(
    settings: Settings,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: _Path,
) -> FastAPI:
    monkeypatch.setattr(settings, "file_storage_dir", tmp_path)
    return _build_app(settings, session_factory)


def test_create_run_is_idempotent_per_request_id(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-idem@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]

        first = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread["id"],
                "request_id": REQUEST_A,
                "message": "帮我找实习",
            },
        )
        assert first.status_code == 202, first.text
        run_id = first.json()["data"]["id"]

        second = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread["id"],
                "request_id": REQUEST_A,
                "message": "帮我找实习",
            },
        )
        assert second.status_code == 202
        assert second.json()["data"]["id"] == run_id

        assert db_session.query(AgentRun).count() == 1


def test_same_request_id_different_payload_conflicts(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-conflict@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]
        client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread["id"],
                "request_id": REQUEST_B,
                "message": "第一次",
            },
        )
        conflict = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread["id"],
                "request_id": REQUEST_B,
                "message": "第二次不同内容",
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "AGENT_REQUEST_CONFLICT"


def test_request_id_is_scoped_per_user(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client_a:
        register_user(client_a, email="run-a@example.com")
        thread_a = client_a.post("/api/v1/agent/threads").json()["data"]
        run_a = client_a.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread_a["id"],
                "request_id": "shared-request-id",
                "message": "A 的请求",
            },
        )
        assert run_a.status_code == 202

        client_b = AutoCsrfTestClient(app, settings)
        register_user(client_b, email="run-b@example.com")
        thread_b = client_b.post("/api/v1/agent/threads").json()["data"]
        run_b = client_b.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread_b["id"],
                "request_id": "shared-request-id",
                "message": "B 的请求",
            },
        )
        assert run_b.status_code == 202
        assert run_b.json()["data"]["id"] != run_a.json()["data"]["id"]

        # User B cannot read user A's run.
        assert client_b.get(f"/api/v1/agent/runs/{run_a.json()['data']['id']}").status_code == 404


def test_events_are_ordered_and_replayable(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-events@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]
        run = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread["id"],
                "request_id": "req-events-1",
                "message": "帮我找实习",
            },
        ).json()["data"]

        listed = client.get(f"/api/v1/agent/runs/{run['id']}/events").json()["data"]
        assert listed, "创建时必须写入 run.queued 事件"
        sequences = [item["sequence"] for item in listed]
        assert sequences == sorted(sequences)
        assert sequences[0] >= 1

        replay = client.get(f"/api/v1/agent/runs/{run['id']}/events?after={sequences[-1]}").json()[
            "data"
        ]
        assert replay == []


def test_cancel_and_cross_user_access(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-cancel@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]
        run = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread["id"],
                "request_id": "req-cancel-1",
                "message": "帮我找实习",
            },
        ).json()["data"]

        cancelled = client.post(f"/api/v1/agent/runs/{run['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["cancel_requested_at"] is not None

        client_b = AutoCsrfTestClient(app, settings)
        register_user(client_b, email="run-cancel-b@example.com")
        assert client_b.post(f"/api/v1/agent/runs/{run['id']}/cancel").status_code == 404


def test_unknown_thread_is_rejected(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-thread@example.com")
        response = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": str(uuid.uuid4()),
                "request_id": "req-unknown-thread",
                "message": "帮我找实习",
            },
        )
        assert response.status_code == 404


def test_finished_run_status_is_not_resurrected(db_session: Session, settings: Settings) -> None:
    from app.agents.run_service import AgentRunService
    from app.db.models.user import User

    user = User(email="run-status@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    from app.db.models.agent_thread import AgentThread

    thread = AgentThread(user_id=user.id, title="t", status="active")
    db_session.add(thread)
    db_session.flush()
    run = AgentRun(
        user_id=user.id,
        thread_id=thread.id,
        request_id="req-status-1",
        status="queued",
        input_payload={"message": "m"},
        attempt_count=0,
    )
    db_session.add(run)
    db_session.flush()

    service = AgentRunService(db_session)
    service.append_event(run, "run.queued", {})
    service.set_status(run, "completed", result={"final_answer": "done"})
    # A late worker must not move a finished run back to running.
    service.set_status(run, "running")
    db_session.refresh(run)
    assert run.status == "completed"

    events = db_session.query(AgentRunEvent).filter_by(run_id=run.id).all()
    assert [e.sequence for e in events] == sorted(e.sequence for e in events)
