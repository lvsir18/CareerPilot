"""Async Agent run endpoints: create (idempotent), poll, SSE, cancel.

The POST returns as soon as the run is persisted; the heavy graph execution
happens in the Celery worker. SSE streams append-only run events so a
disconnected browser can resume with Last-Event-ID.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.agents.run_service import AgentRunService
from app.api.v1.agent import _thread
from app.auth.dependencies import CurrentUser, DbSession
from app.core.errors import AppError
from app.schemas.agent import (
    AgentRunCreate,
    AgentRunEventRead,
    AgentRunRead,
)
from app.schemas.common import DataResponse
from app.security.csrf import require_csrf
from app.workers.tasks import run_agent_run

router = APIRouter(tags=["agent-runs"], dependencies=[Depends(require_csrf)])

_POLL_INTERVAL = 0.7
_MAX_STREAM_SECONDS = 600


def _read(run) -> AgentRunRead:
    return AgentRunRead(
        id=run.id,
        thread_id=run.thread_id,
        request_id=run.request_id,
        status=run.status,
        result=run.result,
        error_code=run.error_code,
        error_summary=run.error_summary,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        cancel_requested_at=run.cancel_requested_at,
        attempt_count=run.attempt_count,
    )


@router.post("/agent/runs", response_model=DataResponse[AgentRunRead], status_code=202)
def create_run(
    payload: AgentRunCreate,
    session: DbSession,
    user: CurrentUser,
) -> DataResponse[AgentRunRead]:
    # Ownership is enforced before any run is created.
    _thread(session, user, payload.thread_id)
    service = AgentRunService(session)
    run, created = service.create_run(
        user_id=user.id,
        thread_id=payload.thread_id,
        request_id=payload.request_id,
        message=payload.message,
    )
    if created:
        # Fire-and-forget dispatch; a failed send leaves the run queued and the
        # reaper (or a retry) can pick it up without duplicating execution.
        with contextlib.suppress(Exception):
            # A broker outage must not fail the API call; the run stays queued.
            run_agent_run.delay(str(run.id))
    return DataResponse(data=_read(run))


@router.get("/agent/runs/{run_id}", response_model=DataResponse[AgentRunRead])
def get_run(
    run_id: UUID,
    session: DbSession,
    user: CurrentUser,
) -> DataResponse[AgentRunRead]:
    run = AgentRunService(session).get_for_user(run_id, user.id)
    return DataResponse(data=_read(run))


@router.get(
    "/agent/runs/{run_id}/events",
    response_model=DataResponse[list[AgentRunEventRead]],
)
def list_run_events(
    run_id: UUID,
    session: DbSession,
    user: CurrentUser,
    after: int = Query(default=0, ge=0),
) -> DataResponse[list[AgentRunEventRead]]:
    service = AgentRunService(session)
    service.get_for_user(run_id, user.id)
    events = service.events_after(run_id, after)
    return DataResponse(
        data=[
            AgentRunEventRead(
                sequence=event.sequence,
                event_type=event.event_type,
                safe_payload=event.safe_payload or {},
                created_at=event.created_at,
            )
            for event in events
        ]
    )


@router.post("/agent/runs/{run_id}/cancel", response_model=DataResponse[AgentRunRead])
def cancel_run(
    run_id: UUID,
    session: DbSession,
    user: CurrentUser,
) -> DataResponse[AgentRunRead]:
    service = AgentRunService(session)
    run = service.get_for_user(run_id, user.id)
    if run.status in {"completed", "failed", "cancelled", "timed_out"}:
        raise AppError(code="AGENT_RUN_FINISHED", message="任务已结束，无法取消", status_code=409)
    # Cooperative cancellation: the worker checks this flag between steps.
    service.request_cancel(run)
    session.refresh(run)
    return DataResponse(data=_read(run))


@router.get("/agent/runs/{run_id}/stream")
async def stream_run(
    run_id: UUID,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    last_event_id: str | None = Query(default=None, alias="lastEventId"),
) -> StreamingResponse:
    """Server-Sent Events backed by the append-only event table."""
    service = AgentRunService(session)
    run = service.get_for_user(run_id, user.id)

    try:
        cursor = int(last_event_id) if last_event_id else 0
    except (TypeError, ValueError):
        cursor = 0

    async def generate():  # type: ignore[no-untyped-def]
        nonlocal cursor
        elapsed = 0.0
        while elapsed < _MAX_STREAM_SECONDS:
            if await request.is_disconnected():
                break
            events = service.events_after(run_id, cursor)
            for event in events:
                payload = {
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "payload": event.safe_payload or {},
                }
                cursor = event.sequence
                yield (
                    f"id: {event.sequence}\n"
                    f"event: {event.event_type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )

            current = session.get(type(run), run_id)
            if current is not None and current.status in {
                "completed",
                "partial",
                "failed",
                "cancelled",
                "timed_out",
                "waiting_for_user",
            }:
                final: dict[str, Any] = {"status": current.status}
                if current.result:
                    final["result"] = current.result
                yield (
                    f"id: {cursor + 1}\n"
                    f"event: run.final\n"
                    f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                )
                break

            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
