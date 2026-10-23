"""LangGraph agent workspace endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.agents.llm import LLMNotConfiguredError
from app.agents.service import AgentService
from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.core.errors import AppError
from app.db.models.agent_thread import AgentThread
from app.schemas.agent import (
    AgentMessageRead,
    AgentResumeRequest,
    AgentRunRequest,
    AgentRunResult,
    AgentThreadRead,
)
from app.schemas.common import DataResponse
from app.security.csrf import require_csrf

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_csrf)])


def _thread_read(thread: AgentThread) -> AgentThreadRead:
    return AgentThreadRead(
        id=thread.id,
        title=thread.title,
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _thread(session: DbSession, user: CurrentUser, thread_id: UUID) -> AgentThread:
    thread = session.scalar(
        select(AgentThread).where(AgentThread.id == thread_id, AgentThread.user_id == user.id)
    )
    if thread is None:
        raise AppError(code="AGENT_THREAD_NOT_FOUND", message="会话不存在", status_code=404)
    return thread


@router.post(
    "/threads",
    response_model=DataResponse[AgentThreadRead],
    summary="新建 Agent 会话",
)
def create_thread(session: DbSession, user: CurrentUser) -> DataResponse[AgentThreadRead]:
    thread = AgentThread(user_id=user.id, title="新对话", status="active")
    session.add(thread)
    session.commit()
    session.refresh(thread)
    return DataResponse(data=_thread_read(thread))


@router.get(
    "/threads",
    response_model=DataResponse[list[AgentThreadRead]],
    summary="列出当前用户会话",
)
def list_threads(session: DbSession, user: CurrentUser) -> DataResponse[list[AgentThreadRead]]:
    threads = session.scalars(
        select(AgentThread)
        .where(AgentThread.user_id == user.id)
        .order_by(AgentThread.updated_at.desc())
    ).all()
    return DataResponse(data=[_thread_read(t) for t in threads])


@router.get(
    "/threads/{thread_id}/messages",
    response_model=DataResponse[list[AgentMessageRead]],
    summary="读取会话历史消息",
)
def list_messages(
    thread_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[list[AgentMessageRead]]:
    _thread(session, user, thread_id)
    history = AgentService(session, settings).history(user, str(thread_id))
    return DataResponse(data=[AgentMessageRead(**item) for item in history])


@router.post(
    "/threads/{thread_id}/runs",
    response_model=DataResponse[AgentRunResult],
    summary="提交消息并执行 Agent 任务（同步）",
)
def run_agent(
    thread_id: UUID,
    payload: AgentRunRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[AgentRunResult]:
    thread = _thread(session, user, thread_id)
    try:
        result = AgentService(session, settings).run(user, str(thread_id), payload.message)
    except LLMNotConfiguredError as exc:
        raise AppError(
            code="LLM_NOT_CONFIGURED",
            message=str(exc),
            status_code=503,
        ) from exc

    if thread.title in {"新对话", ""}:
        thread.title = payload.message[:30] or "新对话"
    thread.updated_at = AgentThread.updated_at  # refresh via commit below
    session.commit()

    return DataResponse(data=AgentRunResult(thread_id=thread_id, **result))


@router.post(
    "/threads/{thread_id}/resume",
    response_model=DataResponse[AgentRunResult],
    summary="从 Human-in-the-Loop 中断恢复",
)
def resume_agent(
    thread_id: UUID,
    payload: AgentResumeRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[AgentRunResult]:
    _thread(session, user, thread_id)
    try:
        result = AgentService(session, settings).resume(user, str(thread_id), payload.approve)
    except LLMNotConfiguredError as exc:
        raise AppError(code="LLM_NOT_CONFIGURED", message=str(exc), status_code=503) from exc
    return DataResponse(data=AgentRunResult(thread_id=thread_id, **result))
