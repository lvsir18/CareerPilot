"""Celery tasks: health probe, job source sync, scheduled fan-out."""

from __future__ import annotations

import socket
import time
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import session_scope
from app.services.job_sync_service import JobSyncService
from app.workers.celery_app import celery_app


@celery_app.task(name="careerpilot.healthcheck")
def healthcheck() -> dict[str, Any]:
    """Round-trip probe proving broker + worker are wired correctly."""
    return {
        "status": "ok",
        "worker": socket.gethostname(),
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


@celery_app.task(name="careerpilot.reconcile_agent_runs")
def reconcile_agent_runs() -> dict[str, Any]:
    """Close agent runs whose worker died, plus cancels nobody ever honoured.

    Without this a restarted worker leaves the run stuck in ``running``: the
    Celery message is re-delivered but ``claim()`` only accepts ``queued``.
    """
    from app.agents.run_service import AgentRunService
    from app.services.email_sync_service import EmailSyncService

    with session_scope() as session:
        fixed = AgentRunService(session).reconcile_stale_runs()
        mailbox_runs = EmailSyncService(session, get_settings()).reconcile_stale_runs()
    # A run left behind by a dying worker is re-queued, not failed: re-dispatch
    # it so the user's question still gets answered after a restart.
    requeued = [item["run_id"] for item in fixed if item.get("status") == "requeued"]
    for run_id in requeued:
        with suppress(Exception):
            run_agent_run.delay(run_id)
    return {"reconciled": fixed, "requeued": len(requeued), "mailbox_runs": mailbox_runs}


@celery_app.task(
    bind=True,
    name="careerpilot.sync_job_source",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=600,
    time_limit=660,
)
def sync_job_source(self, run_id: str) -> dict[str, Any]:
    """Run one queued SyncRun. Duplicate deliveries are de-duplicated by lock."""
    settings = get_settings()
    redis = get_redis()
    lock_key = f"cp:sync:run:{run_id}"

    try:
        acquired = bool(redis.set(lock_key, "1", nx=True, ex=900))
    except Exception:
        # Cache outage must not block synchronization; DB state still guards
        # duplicate terminal runs.
        acquired = True

    if not acquired:
        return {"status": "skipped", "reason": "duplicate_task", "run_id": run_id}

    try:
        with session_scope() as session:
            run = JobSyncService(session, settings).run(UUID(run_id))
            return {
                "status": run.status.value,
                "run_id": str(run.id),
                "source_id": str(run.source_id),
                "fetched": run.fetched_count,
                "created": run.created_count,
                "updated": run.updated_count,
                "unchanged": run.unchanged_count,
                "failed": run.failed_count,
            }
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * (2**self.request.retries)) from exc
        raise
    finally:
        with suppress(Exception):
            redis.delete(lock_key)


@celery_app.task(name="careerpilot.sync_enabled_sources")
def sync_enabled_sources() -> dict[str, Any]:
    """Beat fan-out: queue one run per enabled source, skipping active runs."""
    settings = get_settings()
    if not settings.job_sync_enabled:
        return {"status": "disabled", "queued": 0}

    queued: list[str] = []
    with session_scope() as session:
        service = JobSyncService(session, settings)
        for source in service.list_sources():
            if not source.enabled:
                continue
            if source.source_type == "fixture" and not settings.demo_mode:
                continue
            try:
                run = service.create_run(source.id, None)
            except AppError:
                continue  # active run or disabled source
            sync_job_source.delay(str(run.id))
            queued.append(str(run.id))

    return {"status": "queued", "count": len(queued), "run_ids": queued}


@celery_app.task(
    bind=True,
    name="careerpilot.sync_mailbox",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
)
def sync_mailbox(self, connection_id: str) -> dict[str, Any]:
    """Sync one mailbox with a Redis lock so runs never overlap."""
    from uuid import UUID as _UUID

    from app.db.models.mailbox import MailboxConnection
    from app.services.email_sync_service import EmailSyncService

    settings = get_settings()
    redis = get_redis()
    lock_key = f"cp:mailbox:lock:{connection_id}"
    if not redis.set(lock_key, "1", nx=True, ex=280):
        return {"status": "skipped", "reason": "locked"}
    try:
        with session_scope() as session:
            connection = session.get(MailboxConnection, _UUID(connection_id))
            if connection is None or not connection.sync_enabled:
                return {"status": "skipped", "reason": "disabled"}
            run = EmailSyncService(session, settings).sync_connection(connection)
            return {"status": run.status, "run_id": str(run.id)}
    finally:
        with suppress(Exception):
            redis.delete(lock_key)


@celery_app.task(name="careerpilot.sync_enabled_mailboxes")
def sync_enabled_mailboxes() -> dict[str, Any]:
    """Fan out one sync task per enabled mailbox connection."""
    from sqlalchemy import select as _select

    from app.db.models.mailbox import MailboxConnection

    settings = get_settings()
    if not settings.mailbox_sync_enabled:
        return {"status": "disabled", "queued": 0}
    queued = 0
    with session_scope() as session:
        rows = session.scalars(
            _select(MailboxConnection).where(
                MailboxConnection.sync_enabled.is_(True),
                MailboxConnection.status.in_(["active", "expired", "error"]),
            )
        ).all()
        for row in rows:
            sync_mailbox.delay(str(row.id))
            queued += 1
    return {"status": "ok", "queued": queued}


@celery_app.task(
    bind=True,
    name="careerpilot.run_agent_run",
    max_retries=0,
    soft_time_limit=240,
    time_limit=300,
)
def run_agent_run(self, run_id: str) -> dict[str, Any]:
    """Execute one durable AgentRun in the background.

    Progress is written to ``agent_run_events`` through an independent
    connection so the browser can follow it via SSE while the graph runs.
    """
    from uuid import UUID as _UUID

    from app.agents.run_service import AgentRunCancelled, AgentRunService
    from app.agents.service import AgentService
    from app.core.errors import AppError
    from app.db.models.agent_run import AgentRun
    from app.db.models.user import User
    from app.db.session import session_scope
    from app.services.profile_service import ProfileService
    from app.workers.celery_app import celery_app as _app

    _ = _app

    settings = get_settings()
    run_uuid = _UUID(run_id)
    started = time.time()

    def emit(
        event_type: str, payload: dict[str, Any] | None = None, *, check_cancel: bool = True
    ) -> None:
        with session_scope() as emit_session:
            row = emit_session.get(AgentRun, run_uuid, populate_existing=True)
            if row is None:
                return
            # Cooperative cancellation: events double as graph checkpoints, so a
            # cancel accepted mid-run actually stops the graph instead of being
            # ignored until the final status write.
            if check_cancel and row.cancel_requested_at is not None:
                raise AgentRunCancelled()
            AgentRunService(emit_session).append_event(row, event_type, payload or {})

    with session_scope() as session:
        run = session.get(AgentRun, run_uuid, populate_existing=True)
        if run is None:
            return {"status": "missing"}
        service = AgentRunService(session)
        # Polled at every tool/node boundary; sees the API's cancel write because
        # the query refreshes the identity map.
        cancel_check = lambda: service.is_cancel_requested(run_uuid)  # noqa: E731
        # claim() is the concurrency gate: only one worker moves queued->running.
        if not service.claim(run):
            return {"status": "skipped", "reason": run.status}

        payload = run.input_payload or {}
        resume_payload = payload.get("resume") if isinstance(payload.get("resume"), dict) else None
        user = session.get(User, run.user_id)
        thread_key = str(run.thread_id)
        message = str(payload.get("message", ""))

        # A cancel accepted while the task sat in the queue must win over the
        # work that was about to start.
        if service.is_cancel_requested(run_uuid):
            service.set_status(run, "cancelled")
            emit("run.cancelled", {}, check_cancel=False)
            return {"status": "cancelled"}

        try:
            if resume_payload is not None:
                approve = bool(resume_payload.get("approve", True))
                # Confirmation gates approval, not rejection. A rejection must
                # reach the graph so its interrupt can finish without matching.
                session.expire_all()
                profile = ProfileService(session).get(user)
                if approve and not profile.verified_by_user:
                    service.set_status(run, "waiting_for_user")
                    emit(
                        "approval.required",
                        {
                            "reason": "profile_unconfirmed",
                            "action": "confirm_profile",
                            "message": "画像尚未确认，确认后才能继续匹配",
                        },
                        check_cancel=False,
                    )
                    return {"status": "waiting_for_user"}
                result = AgentService(session, settings).resume(
                    user,
                    thread_key,
                    approve,
                    on_event=emit,
                    cancel_check=cancel_check,
                )
            else:
                result = AgentService(session, settings).run(
                    user, thread_key, message, on_event=emit, cancel_check=cancel_check
                )
        except AgentRunCancelled:
            service.set_status(run, "cancelled")
            emit("run.cancelled", {}, check_cancel=False)
            return {"status": "cancelled"}
        except AppError as exc:
            service.set_status(run, "failed", error_code=exc.code, error_summary=exc.message)
            emit("run.failed", {"code": exc.code, "message": exc.message}, check_cancel=False)
            return {"status": "failed", "code": exc.code}
        except Exception as exc:
            service.set_status(run, "failed", error_code="AGENT_RUN_ERROR", error_summary=str(exc))
            emit(
                "run.failed",
                {"code": "AGENT_RUN_ERROR", "message": str(exc)[:200]},
                check_cancel=False,
            )
            return {"status": "failed"}

        for item in (result.get("tool_results") or [])[:20]:
            try:
                emit(
                    "tool.completed",
                    {"tool": item.get("tool"), "agent": item.get("agent")},
                )
            except AgentRunCancelled:
                service.set_status(run, "cancelled")
                emit("run.cancelled", {}, check_cancel=False)
                return {"status": "cancelled"}

        if service.is_cancel_requested(run_uuid):
            service.set_status(run, "cancelled")
            emit("run.cancelled", {}, check_cancel=False)
            return {"status": "cancelled"}

        raw_status = str(result.get("status") or "")
        if raw_status == "waiting_for_user":
            final = "waiting_for_user"
        elif raw_status == "partial":
            final = "partial"
        elif raw_status == "failed":
            final = "failed"
        else:
            final = "completed"

        service.set_status(
            run,
            final,
            result=result,
            error_summary=(result.get("errors") or [None])[0] if result.get("errors") else None,
        )
        emit(
            {
                "completed": "run.completed",
                "partial": "run.partial",
                "failed": "run.failed",
                "waiting_for_user": "approval.required",
            }[final],
            {"duration_ms": int((time.time() - started) * 1000)},
            check_cancel=False,
        )
        return {"status": final}


@celery_app.task(name="careerpilot.job_refresh")
def job_refresh(run_id: str, recheck: bool = True, discover: bool = False) -> dict[str, Any]:
    """Re-check existing postings and/or discover new ones for one batch."""
    from app.services.job_maintenance_service import JobMaintenanceService

    with session_scope() as session:
        return JobMaintenanceService(session, get_settings()).execute_refresh(
            UUID(run_id), recheck=recheck, discover=discover
        )


@celery_app.task(name="careerpilot.job_prune")
def job_prune(run_id: str) -> dict[str, Any]:
    """Soft-archive postings that carry an explicit closure record."""
    from app.services.job_maintenance_service import JobMaintenanceService

    with session_scope() as session:
        return JobMaintenanceService(session, get_settings()).execute_prune(UUID(run_id))


@celery_app.task(name="careerpilot.job_verify_leads")
def job_verify_leads(run_id: str) -> dict[str, Any]:
    """Verify every pending candidate link of the selected companies."""
    from app.services.job_maintenance_service import JobMaintenanceService

    with session_scope() as session:
        return JobMaintenanceService(session, get_settings()).execute_verify_leads(UUID(run_id))
