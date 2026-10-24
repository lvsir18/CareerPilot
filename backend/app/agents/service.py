"""Agent service: wiring between FastAPI auth, LangGraph graph and checkpointer."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agents.agents import build_specialized_agents
from app.agents.checkpoint import checkpoint_saver
from app.agents.llm import LLMNotConfiguredError, build_chat_model
from app.agents.runtime import (
    AGENT_STATUS_RUNNING,
    AGENT_STATUS_WAITING,
    RuntimeContext,
)
from app.agents.supervisor import build_supervisor
from app.core.config import Settings
from app.db.models.user import User

_HISTORY_ROLES = {"human": "user", "ai": "assistant"}


def _thread_key(user_id: UUID, thread_id: str) -> str:
    return f"{user_id}:{thread_id}"


def _structure_tool_results(tool_results: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Group raw tool payloads into typed cards for the UI (no LLM text parsing)."""
    structured: dict[str, list[Any]] = {
        "jobs": [],
        "matches": [],
        "extra_matches": [],
        "applications": [],
        "progress_events": [],
    }
    for item in tool_results:
        tool = item.get("tool")
        data = item.get("data") or {}
        if not isinstance(data, dict):
            continue
        if tool == "search_jobs":
            structured["jobs"].extend(data.get("jobs") or [])
            structured["jobs"].extend(data.get("leads") or [])
        elif tool == "get_job_detail":
            structured["jobs"].append(data)
        elif tool == "recommend_jobs":
            structured["matches"].extend(data.get("items") or [])
            structured["extra_matches"].extend(data.get("extra_items") or [])
        elif tool == "match_job":
            structured["matches"].append(data)
        elif tool == "list_applications":
            structured["applications"].extend(data.get("applications") or [])
        elif tool == "get_application_timeline":
            structured["progress_events"].extend(data.get("events") or [])
    return structured


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    tool_results = result.get("tool_results") or []
    return {
        "status": result.get("status", AGENT_STATUS_RUNNING),
        "intent": result.get("intent"),
        "constraints": result.get("constraints"),
        "plan": result.get("plan"),
        "agent_results": result.get("agent_results"),
        "final_answer": result.get("final_answer"),
        "errors": result.get("errors", []),
        "structured": _structure_tool_results(tool_results),
    }


class AgentService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def _compile(self, user: User, saver, on_event=None, cancel_check=None, resume_approval=None):
        model = build_chat_model(self._settings)
        if model is None:
            raise LLMNotConfiguredError(
                "未配置 LLM（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），无法执行 Agent 任务"
            )
        ctx = RuntimeContext(
            user_id=user.id,
            user=user,
            session=self._session,
            settings=self._settings,
            on_event=on_event,
            cancel_check=cancel_check,
            resume_approval=resume_approval,
        )
        agents = build_specialized_agents(ctx, model)
        graph = build_supervisor(ctx, model, agents)
        return graph.compile(checkpointer=saver)

    def run(
        self, user: User, thread_id: str, message: str, on_event=None, cancel_check=None
    ) -> dict[str, Any]:
        with checkpoint_saver(self._settings) as saver:
            app = self._compile(user, saver, on_event=on_event, cancel_check=cancel_check)
            config = {"configurable": {"thread_id": _thread_key(user.id, thread_id)}}
            result = app.invoke(
                {"messages": [HumanMessage(content=message)]},
                config=config,
            )
            if "__interrupt__" in result:
                return {"status": AGENT_STATUS_WAITING, "final_answer": None}
        return _summarize(result)

    def resume(
        self, user: User, thread_id: str, approve: bool, cancel_check=None
    ) -> dict[str, Any]:
        with checkpoint_saver(self._settings) as saver:
            app = self._compile(user, saver, cancel_check=cancel_check, resume_approval=approve)
            config = {"configurable": {"thread_id": _thread_key(user.id, thread_id)}}
            result = app.invoke(Command(resume=approve), config=config)
            # Approving may still hit the confirmation gate again; the graph can
            # interrupt a second time and the run has to stay waiting.
            if "__interrupt__" in result:
                return {"status": AGENT_STATUS_WAITING, "final_answer": None}
        return _summarize(result)

    def history(self, user: User, thread_id: str) -> list[dict[str, str]]:
        with checkpoint_saver(self._settings) as saver:
            config = {"configurable": {"thread_id": _thread_key(user.id, thread_id)}}
            state = saver.get_tuple(config)
        if state is None or state.checkpoint is None:
            return []
        messages = state.checkpoint.get("channel_values", {}).get("messages", [])
        result: list[dict[str, str]] = []
        for message in messages:
            role = getattr(message, "type", type(message).__name__)
            # Chat UI only renders the conversation itself; tool call payloads
            # are technical detail and would otherwise leak as raw JSON.
            mapped = _HISTORY_ROLES.get(str(role))
            if mapped is None:
                continue
            content = getattr(message, "content", "")
            if isinstance(content, list):
                content = " ".join(
                    str(part.get("text", "")) if isinstance(part, dict) else str(part)
                    for part in content
                )
            if content:
                result.append({"role": mapped, "content": str(content)})
        return result

    def cancel(self, user: User, thread_id: str) -> None:
        return None
