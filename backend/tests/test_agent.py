from __future__ import annotations

import pytest
from fastapi import FastAPI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session

from app.agents.agents import build_specialized_agents
from app.agents.llm import LLMNotConfiguredError
from app.agents.runtime import RuntimeContext
from app.agents.service import AgentService
from app.agents.supervisor import build_supervisor
from app.agents.tools import build_all_tools
from app.core.config import Settings
from app.db.models.user import User
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user


def _user(db_session: Session, email: str) -> User:
    user = User(email=email, password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


def test_tools_build_and_have_schemas(db_session: Session, settings: Settings) -> None:
    user = _user(db_session, "tools@example.com")
    ctx = RuntimeContext(user_id=user.id, user=user, session=db_session, settings=settings)
    tools = build_all_tools(ctx)
    assert len(tools) == 10
    for tool in tools:
        assert tool.name
        assert tool.args_schema is not None


def test_profile_tool_reads_only_current_user(db_session: Session, settings: Settings) -> None:
    user_a = _user(db_session, "agent-a@example.com")
    ctx_a = RuntimeContext(user_id=user_a.id, user=user_a, session=db_session, settings=settings)
    tool = next(t for t in build_all_tools(ctx_a) if t.name == "get_profile_summary")
    result = tool.invoke({})
    assert result["confirmed"] is False
    assert result["version"] == 0
    assert "agent-a@example.com" not in str(result)


def test_llm_not_configured_raises(db_session: Session, settings: Settings) -> None:
    user = _user(db_session, "nollm@example.com")
    with pytest.raises(LLMNotConfiguredError):
        AgentService(db_session, settings).run(user, "thread-1", "帮我找实习")


def test_supervisor_graph_builds(settings: Settings) -> None:
    model = ChatOpenAI(
        base_url="http://localhost:1/v1", api_key="test", model="test-model", temperature=0
    )
    user = User(email="graph@example.com", password_hash="x")
    ctx = RuntimeContext(
        user_id=user.id,
        user=user,
        session=None,
        settings=settings,  # type: ignore[arg-type]
    )
    agents = build_specialized_agents(ctx, model)
    assert set(agents) == {"job_search", "job_match", "profile", "progress"}
    graph = build_supervisor(ctx, model, agents)
    compiled = graph.compile(checkpointer=MemorySaver())
    assert compiled is not None


def test_agent_thread_isolation(app: FastAPI, settings: Settings, session_factory) -> None:
    with AutoCsrfTestClient(app, settings) as client_a:
        register_user(client_a, email="agent-iso-a@example.com")
        created = client_a.post("/api/v1/agent/threads")
        assert created.status_code == 200
        thread_id = created.json()["data"]["id"]

        client_b = AutoCsrfTestClient(app, settings)
        register_user(client_b, email="agent-iso-b@example.com")
        denied = client_b.get(f"/api/v1/agent/threads/{thread_id}/messages")
        assert denied.status_code == 404


def test_agent_run_requires_llm(app: FastAPI, settings: Settings, session_factory) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="agent-nollm-run@example.com")
        created = client.post("/api/v1/agent/threads").json()["data"]
        run = client.post(
            f"/api/v1/agent/threads/{created['id']}/runs",
            json={"message": "帮我找实习"},
        )
        assert run.status_code == 503
        assert run.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


def test_tool_returns_structured_error_instead_of_raising(
    db_session: Session, settings: Settings
) -> None:
    """A hallucinated job id must not abort the whole agent run."""
    from uuid import uuid4

    user = _user(db_session, "agent-tool-err@example.com")
    ctx = RuntimeContext(user_id=user.id, user=user, session=db_session, settings=settings)
    tools = {tool.name: tool for tool in build_all_tools(ctx)}

    result = tools["get_job_detail"].invoke({"job_id": str(uuid4())})
    assert isinstance(result, dict)
    assert result["error"] == "JOB_NOT_FOUND"
    assert result["message"]
    # Failures are recorded too, so the run is reported as partial instead of
    # silently "completed".
    assert ctx.tool_results[-1]["tool"] == "get_job_detail"
    assert ctx.tool_results[-1]["data"]["error"] == "JOB_NOT_FOUND"


def test_progress_tool_serialises_existing_applications(
    db_session: Session, settings: Settings
) -> None:
    """Regression: the tool read ``app.needs_review`` off the ORM row and died."""
    from app.db.models.enums import ApplicationStatus
    from app.services.application_service import ApplicationService
    from tests.factories import create_job

    user = _user(db_session, "agent-progress@example.com")
    job = create_job(db_session, company="测试科技", title="后端开发实习生")
    ApplicationService(db_session, settings).create(
        user,
        job_id=job.id,
        job_lead_id=None,
        external_company=None,
        external_title=None,
        external_url=None,
        status=ApplicationStatus.APPLIED,
        notes=None,
        applied_at=None,
    )

    ctx = RuntimeContext(user_id=user.id, user=user, session=db_session, settings=settings)
    tool = next(t for t in build_all_tools(ctx) if t.name == "list_applications")
    result = tool.invoke({})

    assert "error" not in result, result
    assert result["total"] == 1
    row = result["applications"][0]
    assert row["company"] == "测试科技"
    assert row["status"] == "applied"
    assert row["needs_review"] is False
    assert row["stale_days"] == 0
