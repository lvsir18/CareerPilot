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
    monkeypatch.setattr(
        "app.agents.service.resolve_chat_model",
        lambda session, settings, user: model,
    )
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
            # The resume path must stream progress too; it used to emit nothing
            # between run.started and the final status.
            assert "agent.started" in resumed_events
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


def test_followup_carries_over_job_type_and_keywords(settings) -> None:
    """「那杭州呢」只换城市，实习与大模型必须保留（否则会混入校招）。"""
    from app.agents.supervisor import _understand

    node = _understand(ScriptedModel("job_search"))
    state = {
        "messages": [
            HumanMessage(content="帮我找北京的大模型实习"),
            AIMessage(content="北京的大模型实习有 20 个"),
            HumanMessage(content="那杭州呢"),
        ],
        "intent": "job_search",
        "constraints": {
            "intent": "job_search",
            "cities": ["北京"],
            "keywords": ["大模型"],
            "job_types": ["实习"],
        },
        "final_answer": "北京的大模型实习有 20 个",
    }

    update = node(state)

    assert update["constraints"]["keywords"] == ["大模型"]
    assert update["constraints"]["job_types"] == ["实习"]
    # 模型没给城市时沿用上一轮；模型给了就以模型为准（见下面的用例）。
    assert update["constraints"]["cities"] == ["北京"]
    assert update["previous_constraints"]["cities"] == ["北京"]
    assert update["previous_question"] == "帮我找北京的大模型实习"
    assert update["previous_answer"] == "北京的大模型实习有 20 个"


def test_explicit_city_wins_over_the_previous_one(settings) -> None:
    """「那杭州呢」：模型给出的城市必须覆盖上一轮的北京。"""
    from langchain_core.messages import AIMessage as _AI

    from app.agents.supervisor import _understand

    class CityModel(ScriptedModel):
        def bind_tools(self, tools):
            def invoke(messages):
                return _AI(
                    content="",
                    tool_calls=[
                        {
                            "name": "Intent",
                            "args": {"intent": "job_search", "cities": ["杭州"]},
                            "id": "i",
                        }
                    ],
                )

            return SimpleNamespace(invoke=invoke)

    node = _understand(CityModel("job_search"))
    update = node(
        {
            "messages": [
                HumanMessage(content="帮我找北京的大模型实习"),
                HumanMessage(content="那杭州呢"),
            ],
            "intent": "job_search",
            "constraints": {
                "intent": "job_search",
                "cities": ["北京"],
                "keywords": ["大模型"],
                "job_types": ["实习"],
            },
        }
    )

    assert update["constraints"]["cities"] == ["杭州"]
    assert update["constraints"]["job_types"] == ["实习"]


def test_chitchat_turn_does_not_break_followup_scope(settings) -> None:
    """「刚才你找到几个」是闲聊轮，不能让下一轮的指代丢失城市。"""
    from app.agents.supervisor import _understand

    node = _understand(ScriptedModel("job_match"))
    state = {
        "messages": [
            HumanMessage(content="帮我找杭州的大模型实习"),
            AIMessage(content="杭州有 8 个岗位"),
            HumanMessage(content="刚才你找到几个"),
            AIMessage(content="我这边没有保留上一次的记录"),
            HumanMessage(content="把第一个岗位的 JD 发我"),
        ],
        "intent": "chitchat",
        "constraints": {"intent": "chitchat"},
        "last_scope": {
            "intent": "job_search",
            "keywords": ["大模型"],
            "companies": [],
            "cities": ["杭州"],
            "job_types": ["实习"],
            "exclude_applied": False,
        },
        "final_answer": "我这边没有保留上一次的记录",
    }

    update = node(state)

    assert update["constraints"]["keywords"] == ["大模型"]
    assert update["constraints"]["job_types"] == ["实习"]
    assert update["constraints"]["cities"] == ["杭州"]


def test_new_intent_does_not_carry_over_scope(settings) -> None:
    """换了意图（找岗位 → 查进度）时不能把上一轮的检索条件带过去。"""
    from app.agents.supervisor import _understand

    node = _understand(ScriptedModel("progress_query"))
    state = {
        "messages": [
            HumanMessage(content="帮我找北京的大模型实习"),
            HumanMessage(content="我的申请进度呢"),
        ],
        "intent": "job_search",
        "constraints": {"intent": "job_search", "keywords": ["大模型"], "job_types": ["实习"]},
    }

    update = node(state)

    assert update["constraints"]["keywords"] == []
    assert update["constraints"]["job_types"] == []


def test_intent_model_receives_the_previous_turn(settings) -> None:
    """The intent model must see the last Q/A, otherwise 指代无法解析。"""
    from app.agents.supervisor import _understand

    captured: dict = {}

    class CapturingModel(ScriptedModel):
        def bind_tools(self, tools):
            def invoke(messages):
                captured.update(json.loads(messages[-1].content))
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "Intent", "args": {"intent": "job_search"}, "id": "i"}],
                )

            return SimpleNamespace(invoke=invoke)

    node = _understand(CapturingModel("job_search"))
    node(
        {
            "messages": [
                HumanMessage(content="帮我找北京的大模型实习"),
                AIMessage(content="北京有 20 个岗位"),
                HumanMessage(content="把第一个岗位的 JD 发我"),
            ],
            "intent": "job_search",
            "constraints": {"cities": ["北京"]},
            "final_answer": "北京有 20 个岗位",
        }
    )

    assert captured["previous"]["question"] == "帮我找北京的大模型实习"
    assert captured["previous"]["answer"] == "北京有 20 个岗位"
    assert captured["previous"]["constraints"]["cities"] == ["北京"]


def test_long_conversation_trims_the_oldest_turns(settings) -> None:
    """长对话不能无限增长；只保留最近若干条，范围由 last_scope 兜底。"""
    from langchain_core.messages import RemoveMessage as _Remove

    from app.agents.supervisor import _understand

    node = _understand(ScriptedModel("job_search"))
    messages = [HumanMessage(content=f"问题 {index}", id=f"m{index}") for index in range(14)]

    update = node({"messages": messages, "intent": "job_search", "constraints": {}})

    removed = update["messages"]
    assert len(removed) == 4  # 14 - keep(10)
    assert all(isinstance(item, _Remove) for item in removed)
    assert [item.id for item in removed] == ["m0", "m1", "m2", "m3"]


def test_short_conversation_keeps_all_messages(settings) -> None:
    from app.agents.supervisor import _understand

    node = _understand(ScriptedModel("chitchat"))
    update = node(
        {
            "messages": [
                HumanMessage(content="你好", id="a"),
                HumanMessage(content="我是谁", id="b"),
            ],
            "intent": "chitchat",
            "constraints": {},
        }
    )

    assert update["messages"] == []


def test_split_matches_filters_cards_by_job_type() -> None:
    """「实习」请求不能把校招岗位混进卡片与推荐。"""
    from app.agents.supervisor import _split_matches

    tool_results = [
        {
            "tool": "search_jobs",
            "data": {
                "jobs": [
                    {
                        "company": "字节跳动",
                        "title": "实习岗",
                        "city": "杭州",
                        "job_type": "internship",
                    },
                    {
                        "company": "字节跳动",
                        "title": "校招岗",
                        "city": "杭州",
                        "job_type": "campus",
                    },
                ],
                "leads": [
                    {
                        "company": "美团",
                        "title": "实习线索",
                        "city": "杭州",
                        "job_type": "internship",
                    },
                    {"company": "美团", "title": "校招线索", "city": "杭州", "job_type": "campus"},
                ],
            },
        }
    ]

    output = _split_matches(tool_results, {"cities": ["杭州"], "job_types": ["实习"]})

    search = next(item for item in output if item["tool"] == "search_jobs")
    assert [job["title"] for job in search["data"]["jobs"]] == ["实习岗"]
    assert [lead["title"] for lead in search["data"]["leads"]] == ["实习线索"]


def test_match_summary_respects_job_type() -> None:
    from app.agents.supervisor import _match_summary

    tool_results = [
        {
            "tool": "import_official_jobs",
            "data": {
                "company": "字节跳动",
                "jobs": [
                    {"title": "实习岗", "city": "杭州", "job_type": "internship"},
                    {"title": "校招岗", "city": "杭州", "job_type": "campus"},
                ],
            },
        }
    ]

    included, _ = _match_summary(tool_results, {"cities": ["杭州"], "job_types": ["实习"]})

    assert [item["title"] for item in included] == ["实习岗"]


def test_preferences_come_from_the_confirmed_profile(monkeypatch) -> None:
    """长期记忆：已确认画像的偏好要进入意图上下文。"""
    from app.agents import supervisor as module

    captured: dict = {}

    class FakeProfile:
        verified_by_user = True
        preferences = SimpleNamespace(
            cities=["成都"],
            job_types=["internship"],
            keywords=["大模型"],
            excluded_keywords=["外包"],
            target_companies=["bytedance"],
        )

    monkeypatch.setattr(
        module.ProfileService, "get", lambda self, user: FakeProfile(), raising=False
    )

    class CapturingModel(ScriptedModel):
        def bind_tools(self, tools):
            def invoke(messages):
                captured.update(json.loads(messages[-1].content))
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "Intent", "args": {"intent": "job_search"}, "id": "i"}],
                )

            return SimpleNamespace(invoke=invoke)

    ctx = SimpleNamespace(session=None, user=None)
    node = module._understand(CapturingModel("job_search"), ctx)
    node({"messages": [HumanMessage(content="帮我找岗位")]})

    assert captured["user_preferences"]["cities"] == ["成都"]
    assert captured["user_preferences"]["job_types"] == ["internship"]
    assert captured["user_preferences"]["excluded_keywords"] == ["外包"]


def test_unconfirmed_profile_contributes_no_preferences(monkeypatch) -> None:
    from app.agents import supervisor as module

    class FakeProfile:
        verified_by_user = False
        preferences = SimpleNamespace(
            cities=["成都"],
            job_types=["internship"],
            keywords=[],
            excluded_keywords=[],
            target_companies=[],
        )

    monkeypatch.setattr(
        module.ProfileService, "get", lambda self, user: FakeProfile(), raising=False
    )

    assert module._preferences(SimpleNamespace(session=None, user=None)) == {}


def test_chat_answers_recall_from_previous_results(settings) -> None:
    """「刚才找到几个」必须引用上一轮统计，而不是说「没保留记录」。"""
    from app.agents.supervisor import _chat

    captured: dict = {}

    class ChatModel:
        def invoke(self, messages):
            captured.update(json.loads(messages[-1].content))
            return AIMessage(content="上一轮杭州找到 8 个岗位")

    node = _chat(ChatModel())
    update = node(
        {
            "messages": [HumanMessage(content="刚才杭州那边你找到几个岗位？")],
            "last_scope": {
                "intent": "job_search",
                "cities": ["杭州"],
                "result_summary": {"jobs": 8, "verified_jobs": 6, "leads": 2},
            },
        }
    )

    assert captured["question"] == "刚才杭州那边你找到几个岗位？"
    assert captured["previous_results"]["jobs"] == 8
    assert captured["previous_results"]["verified_jobs"] == 6
    assert update["final_answer"] == "上一轮杭州找到 8 个岗位"


def test_chat_without_previous_scope_sends_plain_text(settings) -> None:
    from app.agents.supervisor import _chat

    seen: dict = {}

    class ChatModel:
        def invoke(self, messages):
            seen["content"] = messages[-1].content
            return AIMessage(content="你好")

    node = _chat(ChatModel())
    node({"messages": [HumanMessage(content="你好")]})

    assert seen["content"] == "你好"


def test_aggregate_remembers_search_summary() -> None:
    """检索轮要把数量记进 last_scope，供下一轮「刚才找到几个」使用。"""
    from app.agents.supervisor import _aggregate

    node = _aggregate(SimpleNamespace(invoke=lambda messages: AIMessage(content="杭州 2 个岗位")))

    update = node(
        {
            "messages": [HumanMessage(content="帮我找杭州的大模型实习")],
            "intent": "job_search",
            "constraints": {"cities": ["杭州"], "keywords": ["大模型"], "job_types": ["实习"]},
            "tool_results": [
                {
                    "tool": "search_jobs",
                    "data": {
                        "jobs": [{"title": "A", "verification_status": "verified"}],
                        "leads": [{"title": "B", "verification_status": "search_snippet_only"}],
                    },
                },
                {
                    "tool": "import_official_jobs",
                    "data": {"company": "字节跳动", "jobs": [{"title": "C"}]},
                },
            ],
            "last_scope": {"intent": "job_search", "cities": ["杭州"]},
        }
    )

    summary = update["last_scope"]["result_summary"]
    assert summary["jobs"] == 2  # search 1 + official 1
    assert summary["verified_jobs"] == 2  # official imports count as verified
    assert summary["leads"] == 1
    assert summary["cities"] == ["杭州"]
    assert summary["job_types"] == ["实习"]
    assert summary["answer"] == "杭州 2 个岗位"


def test_execute_keeps_readable_tool_error_message() -> None:
    """A failed tool must report *why*: "TOOL_FAILED" alone is not actionable."""
    from app.agents.supervisor import _execute

    class _FakeContext:
        session = None
        user = None
        resume_approval = None
        on_event = None
        cancel_check = None

        def __init__(self) -> None:
            self.tool_results: list[dict] = []

        def ensure_active(self) -> None:
            return None

    node = _execute(_FakeContext(), {})
    state = {
        "messages": [HumanMessage(content="找成都的实习")],
        "constraints": {"required_agents": []},
        "tool_results": [
            {
                "tool": "import_official_jobs",
                "data": {
                    "error": "TOOL_FAILED",
                    "message": "腾讯校招搜索结果缺少 positionList",
                },
            }
        ],
        "agent_results": {},
        "errors": [],
    }

    update = node(state)

    assert update["errors"] == [
        "import_official_jobs: TOOL_FAILED（腾讯校招搜索结果缺少 positionList）"
    ]
    # A tool error means the business task did not succeed.
    assert update["status"] == "partial"


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


def test_split_matches_filters_search_cards_by_city() -> None:
    """Cards must obey the same city/company scope as the answer text."""
    from app.agents.supervisor import _split_matches

    tool_results = [
        {
            "tool": "search_jobs",
            "data": {
                "jobs": [
                    {"company": "字节跳动", "title": "杭州岗位", "city": "杭州"},
                    {"company": "字节跳动", "title": "北京岗位", "city": "北京"},
                ],
                "leads": [
                    {"company": "百度", "title": "杭州线索", "city": "杭州"},
                    {"company": "百度", "title": "上海线索", "city": "上海"},
                ],
            },
        },
        {
            "tool": "import_official_jobs",
            "data": {
                "company": "腾讯",
                "jobs": [{"title": "成都岗位", "city": "成都"}],
            },
        },
    ]

    output = _split_matches(tool_results, {"cities": ["杭州"]})

    search = next(item for item in output if item["tool"] == "search_jobs")
    assert [job["title"] for job in search["data"]["jobs"]] == ["杭州岗位"]
    assert [lead["title"] for lead in search["data"]["leads"]] == ["杭州线索"]
    official = next(item for item in output if item["tool"] == "import_official_jobs")
    assert official["data"]["jobs"] == []


def test_match_summary_includes_search_results() -> None:
    """A pure job_search turn never calls the match tools.

    An empty ``matches`` used to make the summarizer answer "no jobs found"
    while dozens of verified postings sat in the result cards.
    """
    from app.agents.supervisor import _match_summary

    tool_results = [
        {
            "tool": "search_jobs",
            "data": {
                "jobs": [
                    {
                        "id": "job-1",
                        "company": "字节跳动",
                        "title": "AI Agent开发实习生",
                        "city": "北京",
                        "job_type": "internship",
                        "source_url": "https://jobs.example/job-1",
                        "verification_status": "verified",
                    }
                ],
                "leads": [
                    {
                        "id": "lead-2",
                        "company": "百度",
                        "title": "大模型平台后端实习生",
                        "city": "北京",
                        "official_url": "https://jobs.example/lead-2",
                        "verification_status": "search_snippet_only",
                    }
                ],
            },
        },
        {
            "tool": "import_official_jobs",
            "data": {
                "company": "腾讯",
                "jobs": [
                    {
                        "title": "游戏AI算法研究",
                        "city": "成都",
                        "job_type": "internship",
                        "source_url": "https://jobs.example/job-3",
                    }
                ],
            },
        },
    ]

    included, excluded = _match_summary(tool_results, {"cities": ["北京"]})

    assert [item["title"] for item in included] == [
        "AI Agent开发实习生",
        "大模型平台后端实习生",
    ]
    assert included[0]["source"] == "search"
    assert included[0]["verification_status"] == "verified"
    assert included[1]["verification_status"] == "search_snippet_only"
    # Out-of-scope postings are dropped instead of being recommended.
    assert "游戏AI算法研究" not in [item["title"] for item in included]
    assert excluded == 0


def test_match_summary_inherits_company_for_official_imports() -> None:
    from app.agents.supervisor import _match_summary

    tool_results = [
        {
            "tool": "import_official_jobs",
            "data": {
                "company": "腾讯",
                "jobs": [
                    {
                        "title": "游戏AI算法研究",
                        "city": "成都",
                        "job_type": "internship",
                        "source_url": "https://join.qq.com/post_detail.html?postid=1",
                    }
                ],
            },
        }
    ]

    included, _ = _match_summary(tool_results, {"companies": ["腾讯"]})

    assert included[0]["company"] == "腾讯"
    assert included[0]["source"] == "official"
    assert included[0]["verification_status"] == "verified"


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


def test_structure_tool_results_includes_official_imports() -> None:
    """Jobs listed in the answer must also be rendered as cards."""
    from app.agents.service import _structure_tool_results

    structured = _structure_tool_results(
        [
            {
                "tool": "search_jobs",
                "data": {
                    "jobs": [{"id": "1", "title": "搜索到的岗位"}],
                    "leads": [{"id": "2", "title": "摘要线索"}],
                },
            },
            {
                "tool": "import_official_jobs",
                "data": {
                    "company": "腾讯",
                    "jobs": [{"title": "游戏AI算法研究", "city": "成都"}],
                },
            },
        ]
    )

    assert [item.get("title") for item in structured["jobs"]] == [
        "搜索到的岗位",
        "摘要线索",
        "游戏AI算法研究",
    ]
    assert structured["jobs"][2]["company"] == "腾讯"
