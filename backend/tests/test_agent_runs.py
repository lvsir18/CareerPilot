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


def test_same_request_id_different_thread_conflicts(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-thread-conflict@example.com")
        thread_a = client.post("/api/v1/agent/threads").json()["data"]
        thread_b = client.post("/api/v1/agent/threads").json()["data"]
        first = client.post(
            "/api/v1/agent/runs",
            json={"thread_id": thread_a["id"], "request_id": REQUEST_A, "message": "同一句话"},
        )
        assert first.status_code == 202, first.text

        replay = client.post(
            "/api/v1/agent/runs",
            json={"thread_id": thread_b["id"], "request_id": REQUEST_A, "message": "同一句话"},
        )
        assert replay.status_code == 409
        assert replay.json()["error"]["code"] == "AGENT_REQUEST_CONFLICT"
        assert db_session.query(AgentRun).count() == 1


def test_thread_runs_are_listed_newest_first(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-thread-list@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]
        for index, request_id in enumerate(["req-list-1", "req-list-2"]):
            created = client.post(
                "/api/v1/agent/runs",
                json={
                    "thread_id": thread["id"],
                    "request_id": request_id,
                    "message": f"第 {index} 次请求",
                },
            )
            assert created.status_code == 202

        listed = client.get(f"/api/v1/agent/threads/{thread['id']}/runs")
        assert listed.status_code == 200
        runs = listed.json()["data"]
        assert len(runs) == 2
        assert runs[0]["request_id"] == "req-list-2"
        assert runs[0]["thread_id"] == thread["id"]
        for run in runs:
            assert "result" in run and "status" in run


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


def test_stream_emits_final_event_for_finished_run(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-stream@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]
        run = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread["id"],
                "request_id": "req-stream-1",
                "message": "帮我找实习",
            },
        ).json()["data"]

        stored = db_session.get(AgentRun, uuid.UUID(run["id"]))
        assert stored is not None
        stored.status = "completed"
        stored.result = {"summary": "done", "structured": {"jobs": []}}
        db_session.commit()

        with client.stream("GET", f"/api/v1/agent/runs/{run['id']}/stream") as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        assert "event: run.final" in body
        assert '"status": "completed"' in body


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


def _waiting_run(client, db_session: Session) -> dict:
    thread = client.post("/api/v1/agent/threads").json()["data"]
    run = client.post(
        "/api/v1/agent/runs",
        json={"thread_id": thread["id"], "request_id": "req-resume-1", "message": "帮我匹配实习"},
    ).json()["data"]
    stored = db_session.get(AgentRun, uuid.UUID(run["id"]))
    assert stored is not None
    stored.status = "waiting_for_user"
    db_session.commit()
    return {"thread": thread, "run": stored}


def test_resume_requires_confirmed_profile(
    app: FastAPI, settings: Settings, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(
        "app.workers.tasks.run_agent_run.delay", lambda *a, **k: dispatched.append("x")
    )
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-resume-unconfirmed@example.com")
        ctx = _waiting_run(client, db_session)
        dispatched.clear()  # creating the run also dispatches once

        response = client.post(
            f"/api/v1/agent/threads/{ctx['thread']['id']}/resume", json={"approve": True}
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PROFILE_NOT_CONFIRMED"
        db_session.expire_all()
        stored = db_session.get(AgentRun, ctx["run"].id)
        assert stored is not None
        # The run must keep waiting; the client button is not proof.
        assert stored.status == "waiting_for_user"
        assert dispatched == []
        events = db_session.query(AgentRunEvent).filter(AgentRunEvent.run_id == stored.id).all()
        assert any(event.event_type == "approval.required" for event in events)


def test_resume_requeues_run_for_worker(
    app: FastAPI, settings: Settings, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.models.user import User
    from app.services.profile_service import ProfileService

    dispatched: list[str] = []
    monkeypatch.setattr(
        "app.workers.tasks.run_agent_run.delay",
        lambda run_id, *a, **k: dispatched.append(str(run_id)),
    )
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-resume-ok@example.com")
        ctx = _waiting_run(client, db_session)
        dispatched.clear()  # creating the run also dispatches once
        user = db_session.get(User, ctx["run"].user_id)
        assert user is not None
        ProfileService(db_session).confirm(user)
        db_session.commit()

        response = client.post(
            f"/api/v1/agent/threads/{ctx['thread']['id']}/resume", json={"approve": True}
        )

        assert response.status_code == 202, response.text
        body = response.json()["data"]
        assert body["status"] == "queued"
        stored = db_session.get(AgentRun, uuid.UUID(body["id"]))
        assert stored is not None
        db_session.refresh(stored)
        assert stored.status == "queued"
        assert (stored.input_payload or {}).get("resume") == {"approve": True}
        assert dispatched == [str(stored.id)]


def test_stream_resumes_from_last_event_id_header(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-cursor@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]
        run = client.post(
            "/api/v1/agent/runs",
            json={"thread_id": thread["id"], "request_id": "req-cursor", "message": "找工作"},
        ).json()["data"]

        stored = db_session.get(AgentRun, uuid.UUID(run["id"]))
        assert stored is not None
        stored.status = "completed"
        db_session.commit()

        with client.stream(
            "GET",
            f"/api/v1/agent/runs/{run['id']}/stream",
            headers={"Last-Event-ID": "1"},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        # Sequence 1 (run.queued) must not be replayed when the browser reconnects.
        assert "id: 1\n" not in body
        assert "event: run.final" in body


def test_cancel_request_is_seen_after_external_update(
    app: FastAPI, settings: Settings, db_session: Session, session_factory
) -> None:
    """The worker used to keep a stale snapshot and ignore cancellation."""
    from datetime import UTC, datetime

    from app.agents.run_service import AgentRunService

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="run-cancel-fresh@example.com")
        thread = client.post("/api/v1/agent/threads").json()["data"]
        run = client.post(
            "/api/v1/agent/runs",
            json={"thread_id": thread["id"], "request_id": "req-cancel", "message": "找工作"},
        ).json()["data"]

    service = AgentRunService(db_session)
    run_id = uuid.UUID(run["id"])
    assert service.is_cancel_requested(run_id) is False

    other = session_factory()
    try:
        row = other.get(AgentRun, run_id)
        assert row is not None
        row.cancel_requested_at = datetime.now(UTC)
        other.commit()
    finally:
        other.close()

    assert service.is_cancel_requested(run_id) is True
