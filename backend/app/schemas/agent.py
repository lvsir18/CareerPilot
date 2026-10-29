"""Agent workspace contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AgentThreadRead(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class AgentThreadUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    request_id: str | None = Field(default=None, max_length=64)


class AgentResumeRequest(BaseModel):
    approve: bool = True


class AgentMessageRead(BaseModel):
    role: str
    content: str


class AgentRunResult(BaseModel):
    thread_id: UUID
    status: str
    intent: str | None = None
    constraints: dict[str, Any] | None = None
    plan: list[dict[str, Any]] | None = None
    agent_results: dict[str, Any] | None = None
    final_answer: str | None = None
    errors: list[str] = Field(default_factory=list)
    structured: dict[str, Any] | None = None


class AgentRunCreate(BaseModel):
    thread_id: UUID
    request_id: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


class AgentRunRead(BaseModel):
    id: UUID
    thread_id: UUID
    request_id: str
    status: str
    # The question this run answered. The chat page rebuilds one turn per run,
    # so the cards of a turn can stay attached to that turn after a reload.
    input_message: str | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_summary: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    attempt_count: int


class AgentRunEventRead(BaseModel):
    sequence: int
    event_type: str
    safe_payload: dict[str, Any]
    created_at: datetime
