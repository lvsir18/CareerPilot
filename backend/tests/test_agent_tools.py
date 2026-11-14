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


def test_profile_tool_exposes_projects_and_experiences(
    db_session: Session, settings: Settings
) -> None:
    """「我的项目够不够垂直」需要项目正文，不能只说画像里有技能和学历。"""
    from app.agents.tools import build_profile_tools
    from app.db.models.user import User
    from app.schemas.profile import ExperienceItem, ProfileUpdate, ProjectItem
    from app.services.profile_service import ProfileService

    user = User(email="profile-tool@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    ProfileService(db_session).update(
        user,
        ProfileUpdate(
            headline="LLM / Agent 方向",
            skills=["Python", "PyTorch"],
            projects=[
                ProjectItem(
                    title="LLM Agent 评测平台",
                    time_range="2025.03 - 2025.09",
                    summary="负责工具调用编排与轨迹回放，把人工评测成本降低 40%。",
                )
            ],
            experiences=[
                ExperienceItem(
                    kind="internship",
                    title="字节跳动 · 算法实习生",
                    time_range="2025.06 - 2025.09",
                    description="参与 RAG 检索链路优化，召回率提升 6 个百分点。",
                    skills=["PyTorch"],
                )
            ],
        ),
    )

    ctx = RuntimeContext(
        user_id=user.id,
        user=user,
        session=db_session,
        settings=settings,
    )
    tools = {tool.name: tool for tool in build_profile_tools(ctx)}
    data = tools["get_profile_summary"].invoke({})

    assert data["projects"][0]["title"] == "LLM Agent 评测平台"
    assert "轨迹回放" in (data["projects"][0]["summary"] or "")
    assert data["experiences"][0]["title"] == "字节跳动 · 算法实习生"
    assert data["experiences"][0]["skills"] == ["PyTorch"]
    assert data["skills"] == ["Python", "PyTorch"]
