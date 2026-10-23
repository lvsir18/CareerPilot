from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Lock
from time import sleep
from types import SimpleNamespace
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agents.runtime import RuntimeContext
from app.agents.supervisor import build_supervisor
from app.agents.tools import build_profile_tools
from app.db.models.agent_run import AgentRun
from app.db.models.user import User
from app.schemas.profile import ProfileUpdate
from app.services.profile_service import ProfileService
from app.workers.tasks import run_agent_run
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user


class ScriptedModel:
    """Exercise graph/checkpoint behavior without an external model."""

    def __init__(self, intent: str) -> None:
        self.intent = intent
        self.questions: list[str] = []

    def bind_tools(self, tools):
        return SimpleNamespace(
            invoke=lambda messages: AIMessage(
                content="",
                tool_calls=[{"name": "Intent", "args": {"intent": self.intent}, "id": "intent"}],
            )
        )

    def invoke(self, messages):
        payload = json.loads(messages[-1].content)
        self.questions.append(payload["question"])
        return AIMessage(content=payload["question"])


def _agents(calls: list[str]) -> dict:
    def invoke(name):
        def run(payload):
            calls.append(name)
            return {"messages": [AIMessage(content=f"{name} result")]}

        return SimpleNamespace(invoke=run)

    return {name: invoke(name) for name in ("profile", "job_match")}


def test_same_thread_aggregates_the_latest_question(db_session, settings) -> None:
    user = User(email="latest-question@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    model = ScriptedModel("profile_query")
    calls: list[str] = []
    ctx = RuntimeContext(user_id=user.id, user=user, session=db_session, settings=settings)
    graph = build_supervisor(ctx, model, _agents(calls)).compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "two-profile-questions"}}
    first_question = "只回答学历，不要列出城市"
    second_question = "只告诉我目标城市，不要再重复学历"

    first = graph.invoke({"messages": [HumanMessage(content=first_question)]}, config=config)
    second = graph.invoke({"messages": [HumanMessage(content=second_question)]}, config=config)

    assert first["final_answer"] == first_question
    assert second["final_answer"] == second_question
    assert model.questions == [first_question, second_question]
    assert calls == ["profile", "profile"]


def test_parallel_tools_serialize_cancel_checks_and_session_access(
    db_session, settings, monkeypatch
) -> None:
    user = User(email="parallel-tools@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    original_get = ProfileService.get
    guard = Lock()
    active = 0
    peak = 0

    @contextmanager
    def session_operation():
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        try:
            sleep(0.02)  # Let the other tool enter if the session is unguarded.
            yield
        finally:
            with guard:
                active -= 1

    def cancel_check():
        with session_operation():
            return False

    def read_profile(service, current_user):
        with session_operation():
            return original_get(service, current_user)

    monkeypatch.setattr(ProfileService, "get", read_profile)
    ctx = RuntimeContext(
        user_id=user.id,
        user=user,
        session=db_session,
        settings=settings,
        cancel_check=cancel_check,
    )
    tool = next(t for t in build_profile_tools(ctx) if t.name == "get_profile_summary")
    start = Barrier(2)

    def invoke():
        start.wait(timeout=5)
        return tool.invoke({})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]

    assert peak == 1
    assert all("error" not in result for result in results)
    assert len(ctx.tool_results) == 2


@pytest.mark.parametrize("approve", [False, True])
@pytest.mark.parametrize("confirmed_at_execution", [False, True])
def test_hitl_resume_worker_respects_decision_and_confirmation(
    app, settings, db_session, session_factory, monkeypatch, approve, confirmed_at_execution
) -> None:
    """Real API -> worker -> graph interrupt/resume, with independent DB sessions."""
    model = ScriptedModel("job_match")
    saver = MemorySaver()
    calls: list[str] = []

    @contextmanager
    def memory_checkpoint(settings):
        yield saver

    monkeypatch.setattr("app.agents.service.checkpoint_saver", memory_checkpoint)
    monkeypatch.setattr("app.agents.service.build_chat_model", lambda settings: model)
    monkeypatch.setattr(
        "app.agents.service.build_specialized_agents", lambda ctx, model: _agents(calls)
    )
    monkeypatch.setattr("app.workers.tasks.get_settings", lambda: settings)
    monkeypatch.setattr("app.db.session.get_session_factory", lambda: session_factory)
    dispatched: list[str] = []
    monkeypatch.setattr(run_agent_run, "delay", lambda run_id: dispatched.append(run_id))

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="hitl-decision@example.com")
        thread_id = client.post("/api/v1/agent/threads").json()["data"]["id"]
        created = client.post(
            "/api/v1/agent/runs",
            json={
                "thread_id": thread_id,
                "request_id": "hitl-decision",
                "message": "根据画像匹配岗位",
            },
        )
        assert created.status_code == 202
        run_id = created.json()["data"]["id"]
        assert run_agent_run.run(run_id) == {"status": "waiting_for_user"}

        stored = db_session.get(AgentRun, UUID(run_id))
        user = db_session.get(User, stored.user_id)
        profiles = ProfileService(db_session)
        # Approval must pass the API gate. In the stale-profile case it is
        # edited again after dispatch, before the worker executes the resume.
        if approve or confirmed_at_execution:
            profiles.confirm(user)
        dispatched.clear()
        resumed = client.post(
            f"/api/v1/agent/threads/{thread_id}/resume", json={"approve": approve}
        )
        assert resumed.status_code == 202, resumed.text
        assert resumed.json()["data"]["status"] == "queued"
        assert dispatched == [run_id]
        if approve and not confirmed_at_execution:
            profiles.update(user, ProfileUpdate(skills=["Python"]))

        expected = "waiting_for_user" if approve and not confirmed_at_execution else "completed"
        assert run_agent_run.run(run_id) == {"status": expected}
        db_session.refresh(stored)
        assert stored.status == expected
        assert profiles.get(user).verified_by_user is confirmed_at_execution

        events = client.get(f"/api/v1/agent/runs/{run_id}/events").json()["data"]
        decision_index = next(
            i for i, event in enumerate(events) if event["event_type"] == "run.resumed"
        )
        resumed_events = [event["event_type"] for event in events[decision_index + 1 :]]
        if not approve:
            assert "job_match" not in calls
            assert stored.result["agent_results"]["job_match"]["status"] == "declined"
            assert stored.result["structured"]["matches"] == []
            assert "approval.required" not in resumed_events
            assert resumed_events[-1] == "run.completed"
        elif confirmed_at_execution:
            assert calls == ["profile", "job_match"]
            assert resumed_events[-1] == "run.completed"
        else:
            assert calls == []
            assert resumed_events[-1] == "approval.required"
