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


def test_understand_resets_previous_turn_results(settings) -> None:
    """UX3-09: a new question must not inherit the last turn's tool results."""
    from app.agents.supervisor import _understand

    node = _understand(ScriptedModel("profile_query"))
    state = {
        "messages": [HumanMessage(content="只列出我的技术技能")],
        "tool_results": [{"tool": "list_applications", "data": {"total": 1}}],
        "agent_results": {"progress": "上一轮的答案"},
        "errors": ["list_applications: 旧错误"],
        "final_answer": "上一轮结论",
    }

    update = node(state)

    assert update["tool_results"] == []
    assert update["agent_results"] == {}
    assert update["errors"] == []
    assert update["final_answer"] is None


def test_answer_facts_only_carries_progress_tools() -> None:
    """The summarizer gets deterministic progress facts, not giant job payloads."""
    from app.agents.supervisor import _answer_facts

    facts = _answer_facts(
        [
            {"tool": "list_applications", "data": {"total": 1, "applications": []}},
            {"tool": "search_jobs", "data": {"jobs": [{"title": "x"}] * 50}},
            {"tool": "get_application_timeline", "data": {"events": []}},
        ]
    )

    assert [item["tool"] for item in facts] == [
        "list_applications",
        "get_application_timeline",
    ]


def test_matches_are_split_by_the_users_own_constraints() -> None:
    """UX3-04/O-03: the cards must honour company/city/direction, not just eligibility."""
    from app.agents.supervisor import _split_matches

    def entry(company: str, title: str, city: str) -> dict:
        return {"job": {"company": company, "title": title, "city": city}, "match": {}}

    tool_results = [
        {
            "tool": "recommend_jobs",
            "data": {
                "items": [
                    entry("百度", "测试开发工程师（实习生）", "北京"),
                    entry("百度", "数据仓库开发实习生", "北京"),
                    entry("百度", "商家运营实习生", "北京"),
                    entry("字节跳动", "测试开发实习生", "北京"),
                ]
            },
        }
    ]
    constraints = {
        "companies": ["百度"],
        "cities": ["北京"],
        "keywords": ["测试开发", "后端"],
    }

    output = _split_matches(tool_results, constraints)

    kept = [entry["job"]["title"] for item in output for entry in (item["data"].get("items") or [])]
    parked = {
        entry["job"]["title"]: entry["selection_reason"]
        for item in output
        for entry in (item["data"].get("extra_items") or [])
    }
    assert kept == ["测试开发工程师（实习生）"]
    assert parked["数据仓库开发实习生"] == "不在本轮限定的岗位方向"
    assert parked["商家运营实习生"] == "不在本轮限定的岗位方向"
    assert parked["测试开发实习生"] == "不在本轮限定的企业范围"


def test_match_split_is_a_noop_without_constraints() -> None:
    from app.agents.supervisor import _split_matches

    tool_results = [{"tool": "recommend_jobs", "data": {"items": [{"job": {"title": "运营"}}]}}]
    assert _split_matches(tool_results, {}) == tool_results


def test_single_job_match_follows_the_same_scope() -> None:
    from app.agents.supervisor import _split_matches

    tool_results = [
        {
            "tool": "match_job",
            "data": {
                "job": {"company": "百度", "title": "商家运营实习生", "city": "北京"},
                "match": {},
            },
        }
    ]

    output = _split_matches(tool_results, {"companies": ["百度"], "keywords": ["后端"]})

    assert [item["tool"] for item in output] == ["recommend_jobs"]
    assert output[0]["data"]["items"] == []
    assert output[0]["data"]["extra_items"][0]["selection_reason"] == "不在本轮限定的岗位方向"


def test_match_summary_separates_included_from_excluded() -> None:
    from app.agents.supervisor import _match_summary

    tool_results = [
        {
            "tool": "recommend_jobs",
            "data": {
                "items": [
                    {
                        "job": {"company": "百度", "title": "后端开发实习生", "city": "北京"},
                        "match": {"match_score": 72, "eligibility_status": "eligible"},
                    }
                ]
            },
        },
        {
            "tool": "recommend_jobs",
            "data": {
                "items": [],
                "extra_items": [
                    {
                        "job": {"title": "商家运营实习生"},
                        "selection_reason": "不在本轮限定的岗位方向",
                    },
                    {
                        "job": {"title": "数据仓库实习生"},
                        "selection_reason": "不在本轮限定的岗位方向",
                    },
                ],
            },
        },
    ]

    included, excluded = _match_summary(tool_results)

    assert [item["title"] for item in included] == ["后端开发实习生"]
    assert included[0]["match_score"] == 72
    assert excluded == 2


def test_single_job_result_reaches_answer_and_cards() -> None:
    from app.agents.service import _structure_tool_results
    from app.agents.supervisor import _aggregate

    entry = {
        "job": {"company": "百度", "city": "北京", "title": "测试开发实习生"},
        "match": {"match_score": 72, "eligibility_status": "eligible"},
    }
    payloads = []

    def answer(messages):
        payload = json.loads(messages[-1].content)
        payloads.append(payload)
        return AIMessage(content=f"匹配 {payload['matches'][0]['match_score']} 分")

    result = _aggregate(SimpleNamespace(invoke=answer))(
        {
            "messages": [HumanMessage(content="只匹配百度北京测试开发")],
            "intent": "job_match",
            "constraints": {"companies": ["百度"], "cities": ["北京"], "keywords": ["测试开发"]},
            "tool_results": [{"tool": "match_job", "data": entry}],
        }
    )
    assert result["final_answer"] == "匹配 72 分"
    assert payloads[0]["matches"][0]["title"] == entry["job"]["title"]
    assert _structure_tool_results(result["tool_results"])["matches"] == [entry]
