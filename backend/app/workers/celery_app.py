"""Celery application for background syncs and agent runs.

Start the worker with::

    celery -A app.workers.celery_app worker --loglevel=INFO
"""

from __future__ import annotations

from datetime import timedelta

from celery import Celery
from celery.signals import worker_ready

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()

celery_app = Celery(
    "careerpilot",
    broker=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_ignore_result=True,
)

beat_schedule: dict[str, dict[str, object]] = {
    # Zombie runs (worker restarted mid-run) and unhonoured cancels would
    # otherwise stay ``running`` forever.
    "reconcile-agent-runs": {
        "task": "careerpilot.reconcile_agent_runs",
        "schedule": timedelta(minutes=5),
    },
}
if settings.job_sync_enabled:
    beat_schedule["sync-enabled-sources"] = {
        "task": "careerpilot.sync_enabled_sources",
        "schedule": timedelta(minutes=settings.job_sync_interval_minutes),
    }
if settings.mailbox_sync_enabled:
    beat_schedule["sync-enabled-mailboxes"] = {
        "task": "careerpilot.sync_enabled_mailboxes",
        "schedule": timedelta(minutes=settings.mailbox_sync_interval_minutes),
    }
celery_app.conf.beat_schedule = beat_schedule


@worker_ready.connect
def _reconcile_stale_runs_on_start(**_kwargs: object) -> None:
    """A restart is exactly when zombie runs appear, so reconcile immediately."""
    from app.workers.tasks import reconcile_agent_runs

    try:
        reconcile_agent_runs()
    except Exception:  # pragma: no cover - startup must not block the worker
        get_logger(__name__).warning("agent_run_reconcile_failed", exc_info=True)
