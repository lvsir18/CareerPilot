"""Job source synchronization orchestration and audit."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.errors import ConnectorError
from app.connectors.registry import build_connector
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.enums import SyncStatus
from app.db.models.job import Job, JobSource
from app.db.models.sync_run import SyncRun
from app.repositories.job_sources import JobSourceRepository
from app.repositories.sync_runs import SyncRunRepository
from app.services.job_ingestion import InvalidRawJob, upsert_raw_job

logger = get_logger(__name__)

# Config keys an admin may set through the API. Credentials are env-only.
ALLOWED_CONFIG_KEYS = {
    "fixture": set(),
    "manual": {"filename"},
    "alibaba_openapi": {"keyword", "position_url_template", "page_size", "max_pages"},
}


class JobSyncService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._sources = JobSourceRepository(session)
        self._runs = SyncRunRepository(session)

    def _job_count(self, source_id: UUID) -> int:
        return int(
            self._session.scalar(select(func.count(Job.id)).where(Job.source_id == source_id)) or 0
        )

    def create_run(self, source_id: UUID, user_id: UUID | None) -> SyncRun:
        source = self._sources.get(source_id)
        if source is None:
            raise AppError(
                code="JOB_SOURCE_NOT_FOUND",
                message="数据源不存在",
                status_code=404,
            )
        if not source.enabled:
            raise AppError(
                code="JOB_SOURCE_DISABLED",
                message="数据源已禁用",
                status_code=409,
            )
        if self._runs.active_for_source(source_id) is not None:
            raise AppError(
                code="JOB_SYNC_ALREADY_RUNNING",
                message="该数据源已有排队或运行中的同步任务",
                status_code=409,
            )

        run = SyncRun(source_id=source_id, triggered_by_user_id=user_id, status=SyncStatus.QUEUED)
        self._runs.add(run)
        self._session.commit()
        self._session.refresh(run)
        return run

    def mark_failed(self, run_id: UUID, message: str) -> SyncRun | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        run.status = SyncStatus.FAILED
        run.error_message = message[:2000]
        run.ended_at = datetime.now(UTC)
        self._session.commit()
        return run

    def _finish_failure(self, run_id: UUID, message: str) -> SyncRun:
        self._session.rollback()
        run = self._runs.get_for_update(run_id)
        if run is None:  # pragma: no cover - defensive
            raise AppError(code="SYNC_RUN_NOT_FOUND", message="同步任务不存在", status_code=404)
        source = self._sources.get(run.source_id)
        now = datetime.now(UTC)
        run.status = SyncStatus.FAILED
        run.ended_at = now
        run.error_message = message[:2000]
        if source is not None:
            source.last_error = message[:2000]
        self._session.commit()
        self._session.refresh(run)
        return run

    def run(self, run_id: UUID) -> SyncRun:
        run = self._runs.get_for_update(run_id)
        if run is None:
            raise AppError(
                code="SYNC_RUN_NOT_FOUND",
                message="同步任务不存在",
                status_code=404,
            )
        if run.status not in {SyncStatus.QUEUED, SyncStatus.RUNNING}:
            return run

        source = self._sources.get(run.source_id)
        if source is None:
            return self._finish_failure(run.id, "数据源已被删除")
        if not source.enabled:
            return self._finish_failure(run.id, "数据源已禁用")

        run.status = SyncStatus.RUNNING
        run.started_at = datetime.now(UTC)
        self._session.commit()

        try:
            if source.source_type == "fixture" and not self._settings.demo_mode:
                raise ConnectorError("DEMO_MODE=false 时不允许同步演示数据源")

            connector = build_connector(source.source_type, self._settings)
            raw_jobs = connector.fetch_jobs(source.config_json)

            created = updated = unchanged = failed = 0
            for raw in raw_jobs:
                if raw.is_demo and not self._settings.demo_mode:
                    failed += 1
                    continue
                try:
                    outcome = upsert_raw_job(self._session, source, raw)
                except (InvalidRawJob, ValueError) as exc:
                    failed += 1
                    logger.warning(
                        "job_ingest_rejected",
                        extra={
                            "source_type": source.source_type,
                            "source_job_id": raw.source_job_id[:80],
                            "reason": str(exc)[:200],
                        },
                    )
                    continue
                created += int(outcome.created)
                updated += int(outcome.updated)
                unchanged += int(outcome.unchanged)

            now = datetime.now(UTC)
            source.last_success_at = now
            source.last_error = None
            source.last_job_count = self._job_count(source.id)
            run.status = SyncStatus.PARTIAL if failed else SyncStatus.SUCCESS
            run.fetched_count = len(raw_jobs)
            run.created_count = created
            run.updated_count = updated
            run.unchanged_count = unchanged
            run.failed_count = failed
            run.ended_at = now
            self._session.commit()
            self._session.refresh(run)
            logger.info(
                "job_sync_completed",
                extra={
                    "run_id": str(run.id),
                    "source_id": str(source.id),
                    "status": run.status.value,
                    "fetched": run.fetched_count,
                    "failed": run.failed_count,
                },
            )
            return run
        except ConnectorError as exc:
            logger.warning(
                "job_sync_failed",
                extra={
                    "run_id": str(run.id),
                    "source_id": str(source.id),
                    "error_code": exc.code,
                },
            )
            return self._finish_failure(run.id, exc.message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "job_sync_unexpected_error",
                extra={"run_id": str(run.id), "error_type": type(exc).__name__},
            )
            return self._finish_failure(run.id, "同步失败（内部错误）")

    def get_run(self, run_id: UUID) -> SyncRun:
        run = self._runs.get(run_id)
        if run is None:
            raise AppError(code="SYNC_RUN_NOT_FOUND", message="同步任务不存在", status_code=404)
        return run

    def list_runs(self, *, page: int, page_size: int) -> tuple[list[SyncRun], int]:
        return self._runs.list(page=page, page_size=page_size)

    def list_sources(self) -> list[JobSource]:
        return self._sources.list()

    def get_source(self, source_id: UUID) -> JobSource:
        source = self._sources.get(source_id)
        if source is None:
            raise AppError(code="JOB_SOURCE_NOT_FOUND", message="数据源不存在", status_code=404)
        return source

    def update_source(
        self,
        source_id: UUID,
        *,
        enabled: bool | None,
        config: dict[str, object] | None,
    ) -> JobSource:
        source = self.get_source(source_id)
        if enabled is not None:
            source.enabled = enabled
        if config is not None:
            allowed = ALLOWED_CONFIG_KEYS.get(source.source_type, set())
            unknown = set(config) - allowed
            if unknown:
                raise AppError(
                    code="INVALID_SOURCE_CONFIG",
                    message="数据源配置包含不允许的字段",
                    status_code=422,
                    details={"unknown_fields": sorted(unknown)},
                )
            source.config_json = config
        self._session.commit()
        self._session.refresh(source)
        return source
