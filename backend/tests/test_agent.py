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


def test_timeline_tool_returns_events(db_session: Session, settings: Settings) -> None:
    """Regression: the tool read ``event.new_status`` and always failed empty."""
    from datetime import UTC, datetime

    from app.db.models.enums import (
        ApplicationSourceType,
        ApplicationStatus,
        EventVerificationStatus,
    )
    from app.services.application_service import ApplicationService
    from tests.factories import create_job

    user = _user(db_session, "agent-timeline@example.com")
    job = create_job(db_session, company="时间线科技", title="算法实习生")
    service = ApplicationService(db_session, settings)
    application = service.create(
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
    service.add_event(
        user,
        application.id,
        status=ApplicationStatus.INTERVIEW,
        event_time=datetime(2026, 11, 2, 2, 0, tzinfo=UTC),
        note=None,
        evidence_summary="电话通知面试",
        source_type=ApplicationSourceType.MANUAL,
        source_reference=None,
        verification_status=EventVerificationStatus.USER_REPORTED,
    )

    ctx = RuntimeContext(user_id=user.id, user=user, session=db_session, settings=settings)
    tool = next(t for t in build_all_tools(ctx) if t.name == "get_application_timeline")
    result = tool.invoke({"application_id": str(application.id)})

    assert "error" not in result, result
    assert len(result["events"]) >= 2
    interview = next(item for item in result["events"] if item["status"] == "interview")
    assert interview["event_time"].startswith("2026-11-02")
    assert interview["summary"] == "电话通知面试"
    assert interview["appointment"] is True
    # 02:00 UTC is 10:00 in Beijing; the label must be pre-rendered so the model
    # never converts a timezone by itself.
    assert interview["starts_at_label"] == "2026-11-02 10:00（北京时间）"
    assert interview["recorded_at"]
    applied = next(item for item in result["events"] if item["status"] == "applied")
    assert applied["appointment"] is False


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


def test_progress_tools_expose_appointment_and_identifiers(
    db_session: Session, settings: Settings
) -> None:
    """Regression: the assistant denied a scheduled interview and mismatched ids."""
    from datetime import UTC, datetime, timedelta

    from app.db.models.enums import (
        ApplicationSourceType,
        ApplicationStatus,
        EventVerificationStatus,
    )
    from app.services.application_service import ApplicationService
    from tests.factories import create_job

    user = _user(db_session, "agent-next@example.com")
    # A real source_job_id is the id from the official detail URL, not the number
    # printed in the title.
    job = create_job(
        db_session,
        company="百度",
        title="测试开发实习生",
        source_job_id="24666ec4-e770-4827-8fb9-6a6d165f4376",
    )
    service = ApplicationService(db_session, settings)
    application = service.create(
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
    starts_at = datetime.now(UTC) + timedelta(days=2)
    service.add_event(
        user,
        application.id,
        status=ApplicationStatus.INTERVIEW,
        event_time=starts_at,
        note=None,
        evidence_summary="HR 电话约定一面",
        source_type=ApplicationSourceType.MANUAL,
        source_reference=None,
        verification_status=EventVerificationStatus.USER_REPORTED,
    )

    ctx = RuntimeContext(user_id=user.id, user=user, session=db_session, settings=settings)
    tools = {tool.name: tool for tool in build_all_tools(ctx)}

    listed = tools["list_applications"].invoke({})
    assert "error" not in listed, listed
    row = listed["applications"][0]
    assert row["job_no"] == "24666ec4-e770-4827-8fb9-6a6d165f4376"
    assert row["job_id"] == str(job.id)
    assert row["application_id"] == str(application.id)
    assert row["next_appointment"]["starts_at_label"].endswith("（北京时间）")

    for identifier in (
        str(application.id),
        str(job.id),
        "24666ec4-e770-4827-8fb9-6a6d165f4376",
    ):
        checked = tools["check_job_application_status"].invoke({"identifier": identifier})
        assert checked["applied"] is True, (identifier, checked)
        assert checked["status"] == "interview"

    for unknown_value in ("999999", "J106720"):
        unknown = tools["check_job_application_status"].invoke({"identifier": unknown_value})
        # Neither a stray number nor the title's display code may masquerade as
        # "not applied".
        assert unknown["error"] == "IDENTIFIER_NOT_RECOGNIZED"


def test_appointment_keeps_confirmation_time_in_the_past(
    db_session: Session, settings: Settings
) -> None:
    """UX3-11: a future slot must not become ``last_confirmed_at``."""
    from datetime import UTC, datetime, timedelta

    from app.db.models.enums import (
        ApplicationSourceType,
        ApplicationStatus,
        EventVerificationStatus,
    )
    from app.services.application_service import ApplicationService
    from tests.factories import create_job

    user = _user(db_session, "agent-confirm-time@example.com")
    job = create_job(db_session, company="预约科技", title="后端实习生")
    service = ApplicationService(db_session, settings)
    application = service.create(
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
    service.add_event(
        user,
        application.id,
        status=ApplicationStatus.INTERVIEW,
        event_time=datetime.now(UTC) + timedelta(days=5),
        note=None,
        evidence_summary="约定面试",
        source_type=ApplicationSourceType.MANUAL,
        source_reference=None,
        verification_status=EventVerificationStatus.USER_REPORTED,
    )

    refreshed = service.get(user, application.id)
    assert refreshed.last_confirmed_at is not None
    assert refreshed.last_confirmed_at < datetime.now(UTC) + timedelta(minutes=1)


def test_progress_timeline_marks_retired_appointments_and_keeps_active_next(
    db_session: Session, settings: Settings
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.models.enums import (
        ApplicationSourceType,
        ApplicationStatus,
        EventVerificationStatus,
    )
    from app.services.application_service import ApplicationService
    from tests.factories import create_job

    user = _user(db_session, "retired-appointments@example.com")
    job = create_job(db_session)
    service = ApplicationService(db_session, settings)
    application = service.create(
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

    def appointment(days, target=None):
        return service.add_event(
            user,
            application.id,
            status=ApplicationStatus.INTERVIEW,
            event_time=datetime.now(UTC) + timedelta(days=days),
            note=None,
            evidence_summary=None,
            source_type=ApplicationSourceType.MANUAL,
            source_reference=None,
            verification_status=EventVerificationStatus.USER_REPORTED,
            reschedule_event_id=target,
        )

    old = appointment(1)
    active = appointment(2, old.id)
    cancelled = appointment(3)
    service.cancel_event(user, application.id, cancelled.id)
    tools = {
        t.name: t
        for t in build_all_tools(
            RuntimeContext(user_id=user.id, user=user, session=db_session, settings=settings)
        )
    }
    rows = tools["get_application_timeline"].invoke({"application_id": str(application.id)})[
        "events"
    ]
    scheduled = [r for r in rows if r["is_scheduled"]]
    assert len(scheduled) == 3
    assert [r["appointment_state"] for r in scheduled] == ["inactive", "active", "inactive"]
    assert [r["appointment"] for r in scheduled] == [False, True, False]
    assert all(r["superseded_at"] for r in scheduled if not r["appointment"])
    next_slot = tools["list_applications"].invoke({})["applications"][0]["next_appointment"]
    assert datetime.fromisoformat(next_slot["starts_at"]) == active.event_time
