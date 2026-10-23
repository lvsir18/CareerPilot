from __future__ import annotations

from contextlib import contextmanager

from fakeredis import FakeRedis

import app.workers.tasks as tasks
from app.core.config import Settings
from app.db.models.job import JobSource
from app.db.models.sync_run import SyncRun
from app.services.job_sync_service import JobSyncService


class _RecordingTask:
    def __init__(self) -> None:
        self.run_ids: list[str] = []

    def delay(self, run_id: str) -> None:
        self.run_ids.append(run_id)


def test_sync_task_runs_service_and_dedupes_by_lock(
    db_session, settings: Settings, monkeypatch
) -> None:
    source = JobSource(
        source_type="fixture", source_key="task-fixture", config_json={}, enabled=True
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    service = JobSyncService(db_session, settings)
    run = service.create_run(source.id, None)

    fake_redis = FakeRedis(decode_responses=True)

    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(tasks, "session_scope", fake_session_scope)

    result = tasks.sync_job_source.run(str(run.id))
    assert result["status"] == "success"
    assert result["created"] == 8

    # A duplicate delivery while the lock is held must not re-run the sync.
    duplicate_run = service.create_run(source.id, None)
    fake_redis.set(f"cp:sync:run:{duplicate_run.id}", "1", ex=60)
    skipped = tasks.sync_job_source.run(str(duplicate_run.id))
    assert skipped["status"] == "skipped"


def test_scheduled_fanout_queues_enabled_sources(
    db_session, settings: Settings, monkeypatch
) -> None:
    source = JobSource(
        source_type="fixture", source_key="fanout-fixture", config_json={}, enabled=True
    )
    db_session.add(source)
    db_session.commit()
    recording = _RecordingTask()

    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(
        tasks, "get_settings", lambda: settings.model_copy(update={"job_sync_enabled": True})
    )
    monkeypatch.setattr(tasks, "session_scope", fake_session_scope)
    monkeypatch.setattr(tasks, "sync_job_source", recording)

    result = tasks.sync_enabled_sources.run()

    assert result["status"] == "queued"
    assert result["count"] == 1
    assert len(recording.run_ids) == 1
    assert db_session.query(SyncRun).count() == 1


def test_scheduled_fanout_is_disabled_by_default(
    db_session, settings: Settings, monkeypatch
) -> None:
    @contextmanager
    def fake_session_scope():
        yield db_session

    monkeypatch.setattr(tasks, "session_scope", fake_session_scope)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)

    assert tasks.sync_enabled_sources.run()["status"] == "disabled"
