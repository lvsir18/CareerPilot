from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agents.runtime import RuntimeContext
from app.agents.tools import _safe_tool, build_job_tools
from app.core.config import Settings
from tests.factories import create_job


def _job_tools(session: Session, settings: Settings) -> dict[str, object]:
    ctx = RuntimeContext(
        user_id=uuid4(),
        user=SimpleNamespace(email="agent-tools@example.com"),  # type: ignore[arg-type]
        session=session,
        settings=settings,
    )
    return {tool.name: tool for tool in build_job_tools(ctx)}


def test_get_job_detail_accepts_official_posting_number(
    db_session: Session, settings: Settings
) -> None:
    """LLMs pass the number printed on the official site, not our UUID."""
    job = create_job(
        db_session,
        source_job_id="1231829074692139126",
        title="游戏AI算法研究",
        city="成都",
    )
    tools = _job_tools(db_session, settings)

    detail = tools["get_job_detail"].invoke({"job_id": "1231829074692139126"})

    assert detail["id"] == str(job.id)
    assert detail["title"] == "游戏AI算法研究"
    assert detail["city"] == "成都"


def test_get_job_detail_explains_lead_ids(db_session: Session, settings: Settings) -> None:
    """A lead id is not a job id: answer with a pointer instead of ValueError."""
    tools = _job_tools(db_session, settings)

    result = tools["get_job_detail"].invoke({"job_id": str(uuid4())})

    assert result["error"] == "JOB_NOT_FOUND"
    assert "leads" in result["message"]
    assert "official_url" in result["message"]


def test_find_job_hides_demo_postings_outside_demo_mode(
    db_session: Session, settings: Settings
) -> None:
    demo = create_job(db_session, source_job_id="demo-9001", is_demo=True)
    tools = _job_tools(db_session, settings.model_copy(update={"demo_mode": False}))

    by_number = tools["get_job_detail"].invoke({"job_id": "demo-9001"})
    by_uuid = tools["get_job_detail"].invoke({"job_id": str(demo.id)})

    assert by_number["error"] == "JOB_NOT_FOUND"
    assert by_uuid["error"] == "JOB_NOT_FOUND"


def test_safe_tool_emits_progress_events(settings: Settings) -> None:
    """The UI keeps a frozen "sub-task running" unless tools report progress."""
    events: list[tuple[str, dict[str, Any]]] = []
    ctx = RuntimeContext(
        user_id=uuid4(),
        user=SimpleNamespace(email="agent-tools@example.com"),  # type: ignore[arg-type]
        session=None,  # type: ignore[arg-type]
        settings=settings,
        on_event=lambda event_type, payload=None: events.append((event_type, payload or {})),
    )

    @_safe_tool(ctx)
    def demo_tool(value: int) -> dict[str, Any]:
        return {"error": "DEMO_ERROR", "message": f"got {value}"}

    result = demo_tool(1)

    assert result == {"error": "DEMO_ERROR", "message": "got 1"}
    assert [event[0] for event in events] == ["tool.started", "tool.completed"]
    assert events[0][1] == {"tool": "demo_tool"}
    assert events[1][1] == {"tool": "demo_tool", "ok": False}
