from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks import healthcheck


def test_celery_is_configured_with_json_and_utc() -> None:
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.broker_url.endswith("/0")
    assert "app.workers.tasks" in celery_app.conf.include


def test_healthcheck_task_runs_without_broker() -> None:
    result = healthcheck.run()

    assert result["status"] == "ok"
    assert result["checked_at"].endswith("Z")
    assert result["worker"]
