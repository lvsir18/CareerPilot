"""Durable agent run lifecycle: idempotent creation, state machine, event log.

Invariants:
- ``request_id`` is unique per user, so retries never create a second run.
- Once a run reaches a terminal state it is never moved back to ``running``.
- Events are append-only with a monotonically increasing per-run sequence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.runtime import RunCancelled
from app.core.errors import AppError
from app.db.models.agent_run import AgentRun, AgentRunEvent

TERMINAL_STATUSES = frozenset({"completed", "partial", "failed", "cancelled", "timed_out"})

# States an already-finished run must never be overwritten with.
_PROTECTED_FROM = frozenset({"queued", "running", "waiting_for_user"})

# A worker killed mid-run leaves the row in ``running`` forever. These bounds
# decide when that zombie (or an unhonoured cancel) gets reconciled.
STALE_RUN_TIMEOUT_SECONDS = 900  # > 3 × Celery soft_time_limit (240s)
CANCEL_GRACE_SECONDS = 60


def _seconds_since(value: datetime, now: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (now - value).total_seconds()


# Re-exported so worker code has a single exception type to catch.
AgentRunCancelled = RunCancelled


class AgentRunService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------------------------------------------------------------- create
    def create_run(
        self,
        *,
        user_id: UUID,
        thread_id: UUID,
        request_id: str,
        message: str,
    ) -> tuple[AgentRun, bool]:
        """Return ``(run, created)``. Re-submission returns the existing run."""
        existing = self._session.scalar(
            select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.request_id == request_id)
        )
        if existing is not None:
            self._assert_same_request(existing, thread_id=thread_id, message=message)
            return existing, False

        run = AgentRun(
            user_id=user_id,
            thread_id=thread_id,
            request_id=request_id,
            status="queued",
            input_payload={"message": message},
            attempt_count=0,
        )
        self._session.add(run)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            concurrent = self._session.scalar(
                select(AgentRun).where(
                    AgentRun.user_id == user_id, AgentRun.request_id == request_id
                )
            )
            if concurrent is not None:
                self._assert_same_request(concurrent, thread_id=thread_id, message=message)
                return concurrent, False
            raise AppError(
                code="AGENT_RUN_CREATE_FAILED", message="创建任务失败", status_code=500
            ) from exc
        self.append_event(run, "run.queued", {"run_id": str(run.id)})
        self._session.commit()
        self._session.refresh(run)
        return run, True

    @staticmethod
    def _assert_same_request(existing: AgentRun, *, thread_id: UUID, message: str) -> None:
        """A replayed request_id must match both the thread and the message."""
        if existing.input_payload.get("message") != message or existing.thread_id != thread_id:
            raise AppError(
                code="AGENT_REQUEST_CONFLICT",
                message="同一 request_id 已用于不同的请求内容或会话",
                status_code=409,
            )

    # ----------------------------------------------------------------- state
    def set_status(
        self,
        run: AgentRun,
        status: str,
        *,
        error_code: str | None = None,
        error_summary: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        if run.status in TERMINAL_STATUSES and status in _PROTECTED_FROM:
            # Late worker results must not resurrect a finished run.
            return
        run.status = status
        if status == "running" and run.started_at is None:
            run.started_at = now
        if status in TERMINAL_STATUSES:
            run.finished_at = now
        if error_code is not None:
            run.error_code = error_code
        if error_summary is not None:
            run.error_summary = error_summary[:500]
        if result is not None:
            run.result = result
        self._session.commit()

    def request_cancel(self, run: AgentRun) -> None:
        run.cancel_requested_at = datetime.now(UTC)
        self.append_event(run, "run.cancel_requested", {})
        self._session.commit()

    def is_cancel_requested(self, run_id: UUID) -> bool:
        # The API writes the flag in a different transaction; the identity map
        # would keep serving the pre-cancel snapshot for the whole worker run.
        run = self._session.get(AgentRun, run_id, populate_existing=True)
        return run is not None and run.cancel_requested_at is not None

    def claim(self, run: AgentRun) -> bool:
        """Atomically move queued -> running; False if another worker won."""
        if run.status != "queued":
            return False
        run.status = "running"
        run.started_at = datetime.now(UTC)
        run.attempt_count += 1
        self.append_event(run, "run.started", {"attempt": run.attempt_count})
        self._session.commit()
        return True

    def reconcile_stale_runs(
        self,
        *,
        now: datetime | None = None,
        run_timeout_seconds: int = STALE_RUN_TIMEOUT_SECONDS,
        cancel_grace_seconds: int = CANCEL_GRACE_SECONDS,
    ) -> list[dict[str, Any]]:
        """Close runs left behind by a dead worker.

        A worker that is restarted or killed mid-run leaves ``status='running'``
        forever: Celery re-delivers the message (``acks_late``), but ``claim()``
        only accepts ``queued``. A cancel accepted while no worker was alive has
        the same fate. Both are reconciled here instead of waiting for the user
        to give up on a spinner.
        """
        moment = now or datetime.now(UTC)
        runs = self._session.scalars(
            select(AgentRun).where(AgentRun.status.in_(("queued", "running")))
        ).all()
        reconciled: list[dict[str, Any]] = []
        for run in runs:
            cancelled_at = run.cancel_requested_at
            if cancelled_at is not None and (
                _seconds_since(cancelled_at, moment) >= cancel_grace_seconds
            ):
                self.append_event(run, "run.cancelled", {"reason": "no_worker"})
                self.set_status(run, "cancelled")
                reconciled.append({"run_id": str(run.id), "status": "cancelled"})
                continue
            started_at = run.started_at
            if (
                started_at is not None
                and run_timeout_seconds > 0
                and _seconds_since(started_at, moment) >= run_timeout_seconds
            ):
                summary = "执行进程中断（Worker 重启或崩溃），本轮未产出结果，请重试"
                self.append_event(
                    run, "run.failed", {"code": "RUN_INTERRUPTED", "message": summary}
                )
                self.set_status(
                    run,
                    "failed",
                    error_code="RUN_INTERRUPTED",
                    error_summary=summary,
                )
                reconciled.append({"run_id": str(run.id), "status": "failed"})
        return reconciled

    # ---------------------------------------------------------------- events
    def append_event(
        self, run: AgentRun, event_type: str, payload: dict[str, Any]
    ) -> AgentRunEvent:
        next_seq = self._session.scalar(
            select(func.coalesce(func.max(AgentRunEvent.sequence), 0) + 1).where(
                AgentRunEvent.run_id == run.id
            )
        )
        event = AgentRunEvent(
            run_id=run.id,
            sequence=int(next_seq or 1),
            event_type=event_type,
            safe_payload=payload or {},
            created_at=datetime.now(UTC),
        )
        self._session.add(event)
        self._session.flush()
        return event

    def events_after(self, run_id: UUID, last_sequence: int) -> list[AgentRunEvent]:
        return list(
            self._session.scalars(
                select(AgentRunEvent)
                .where(
                    AgentRunEvent.run_id == run_id,
                    AgentRunEvent.sequence > last_sequence,
                )
                .order_by(AgentRunEvent.sequence.asc())
            )
        )

    # ------------------------------------------------------------------ read
    def get_for_user(self, run_id: UUID, user_id: UUID) -> AgentRun:
        run = self._session.get(AgentRun, run_id)
        if run is None or run.user_id != user_id:
            raise AppError(code="AGENT_RUN_NOT_FOUND", message="任务不存在", status_code=404)
        return run

    def list_for_thread(self, thread_id: UUID, user_id: UUID) -> list[AgentRun]:
        return list(
            self._session.scalars(
                select(AgentRun)
                .where(AgentRun.thread_id == thread_id, AgentRun.user_id == user_id)
                .order_by(AgentRun.created_at.desc())
                .limit(50)
            )
        )
