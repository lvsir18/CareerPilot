"""LangGraph agent workspace endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from app.agents.llm import LLMNotConfiguredError
from app.agents.run_service import AgentRunService
from app.agents.service import AgentService
from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.core.errors import AppError
from app.db.models.agent_run import AgentRun
from app.db.models.agent_thread import AgentThread
from app.schemas.agent import (
    AgentMessageRead,
    AgentResumeRequest,
    AgentRunRequest,
    AgentRunResult,
    AgentThreadRead,
    AgentThreadUpdate,
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


@router.patch(
    "/threads/{thread_id}",
    response_model=DataResponse[AgentThreadRead],
    summary="重命名会话",
)
def rename_thread(
    thread_id: UUID,
    payload: AgentThreadUpdate,
    session: DbSession,
    user: CurrentUser,
) -> DataResponse[AgentThreadRead]:
    thread = _thread(session, user, thread_id)
    title = " ".join(payload.title.split())
    if not title:
        raise AppError(
            code="AGENT_THREAD_TITLE_REQUIRED", message="会话名称不能为空", status_code=422
        )
    thread.title = title[:80]
    session.commit()
    session.refresh(thread)
    return DataResponse(data=_thread_read(thread))


@router.delete(
    "/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除会话（同时删除其运行记录与事件）",
)
def delete_thread(thread_id: UUID, session: DbSession, user: CurrentUser) -> Response:
    thread = _thread(session, user, thread_id)
    # agent_runs 与 agent_run_events 通过外键 ON DELETE CASCADE 一并清理。
    session.delete(thread)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    # Rebuild the transcript from persisted runs: the graph checkpoint only
    # stores the human turn plus tool traffic, so the final answer would be
    # missing after a reload. Runs keep both the prompt and the answer.
    runs = session.scalars(
        select(AgentRun)
        .where(AgentRun.thread_id == thread_id, AgentRun.user_id == user.id)
        .order_by(AgentRun.created_at.asc())
    ).all()
    messages: list[AgentMessageRead] = []
    for run in runs:
        prompt = (run.input_payload or {}).get("message")
        if isinstance(prompt, str) and prompt.strip():
            messages.append(AgentMessageRead(role="user", content=prompt))
        result = run.result if isinstance(run.result, dict) else None
        answer = result.get("final_answer") if result else None
        if isinstance(answer, str) and answer.strip():
            messages.append(AgentMessageRead(role="assistant", content=answer))
    if messages:
        return DataResponse(data=messages)

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
    run_service = AgentRunService(session)
    # The interrupted run is the one the user is being asked about; keep its row
    # in sync so the conversation (and any open stream) shows the real outcome
    # instead of leaving it stuck at waiting_for_user.
    waiting = next(
        (
            item
            for item in run_service.list_for_thread(thread_id, user.id)
            if item.status == "waiting_for_user"
        ),
        None,
    )
    if waiting is not None:
        run_service.set_status(waiting, "running")
        run_service.append_event(waiting, "run.resumed", {"approve": payload.approve})
        session.commit()

    try:
        result = AgentService(session, settings).resume(user, str(thread_id), payload.approve)
    except LLMNotConfiguredError as exc:
        if waiting is not None:
            run_service.set_status(
                waiting, "failed", error_code="LLM_NOT_CONFIGURED", error_summary=str(exc)[:500]
            )
        raise AppError(code="LLM_NOT_CONFIGURED", message=str(exc), status_code=503) from exc
    if waiting is not None:
        status = result.get("status") or "completed"
        run_service.append_event(waiting, "run.final", {"status": status})
        run_service.set_status(waiting, status, result=result)
    return DataResponse(data=AgentRunResult(thread_id=thread_id, **result))
