"""Trusted runtime context and agent graph state.

User identity is injected by the FastAPI authentication layer, never derived
from LLM-generated tool arguments.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from langgraph.graph.message import add_messages
from sqlalchemy.orm import Session
from typing_extensions import TypedDict

from app.core.config import Settings
from app.db.models.user import User

# Agent status is a fixed state machine, not free text.
AGENT_STATUS_CREATED = "created"
AGENT_STATUS_RUNNING = "running"
AGENT_STATUS_WAITING = "waiting_for_user"
AGENT_STATUS_COMPLETED = "completed"
AGENT_STATUS_PARTIAL = "partial"
AGENT_STATUS_FAILED = "failed"
AGENT_STATUS_CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Per-request trusted context. Never populated from LLM output."""

    user_id: UUID
    user: User
    session: Session
    settings: Settings
    # Optional sink for execution progress events (SSE replay). Never set
    # from model output.
    on_event: Callable[..., None] | None = None
    # Every tool call records its result here. Structured result cards read this
    # instead of parsing ToolMessage content, whose serialisation is up to the
    # model/tool node and silently varies between "{}" and "{'k': 'v'}".
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    def record_tool(self, tool: str, data: Any) -> None:
        try:
            # Snapshot: later mutation by the caller must not rewrite history.
            snapshot = json.loads(json.dumps(data, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            snapshot = {"error": "TOOL_OUTPUT_UNSERIALIZABLE", "message": str(data)[:300]}
        self.tool_results.append({"tool": tool, "data": snapshot})

    def model_dump_scoped(self) -> dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "email_domain": (self.user.email or "").split("@")[-1],
        }


class CareerAgentState(TypedDict, total=False):
    """Shared graph state. Sensitive payloads stay in services, not here."""

    messages: Annotated[list[Any], add_messages]
    task_id: str
    intent: str
    constraints: dict[str, Any]
    plan: list[dict[str, Any]]
    current_step: int
    agent_results: dict[str, Any]
    tool_results: list[dict[str, Any]]
    status: str
    errors: list[str]
    final_answer: str | None
