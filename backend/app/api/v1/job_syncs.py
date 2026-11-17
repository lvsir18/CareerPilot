"""Admin-only sync trigger and audit endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import AdminUser, AppSettings, DbSession
from app.core.errors import AppError
from app.schemas.common import DataResponse, Page, PageMeta
from app.schemas.sources import SyncRequest, SyncRunRead, sync_run_to_read
from app.security.csrf import require_csrf
from app.services.job_sync_service import JobSyncService
from app.workers.tasks import sync_job_source

router = APIRouter(prefix="/job-syncs", tags=["job-syncs"], dependencies=[Depends(require_csrf)])


@router.post(
    "",
    response_model=DataResponse[SyncRunRead],
    status_code=status.HTTP_202_ACCEPTED,
    summary="管理员触发单个数据源同步（Celery 异步执行）",
)
def trigger_sync(
    payload: SyncRequest,
    session: DbSession,
    settings: AppSettings,
    admin: AdminUser,
) -> DataResponse[SyncRunRead]:
    service = JobSyncService(session, settings)
    run = service.create_run(payload.source_id, admin.id)
    try:
        sync_job_source.delay(str(run.id))
    except Exception as exc:  # broker unavailable
        service.mark_failed(run.id, "任务队列不可用，未能入队")
        raise AppError(
            code="SYNC_QUEUE_UNAVAILABLE",
            message="任务队列暂不可用，请稍后重试",
            status_code=503,
        ) from exc
    return DataResponse(data=sync_run_to_read(run))


@router.get(
    "",
    response_model=Page[SyncRunRead],
    summary="同步任务记录",
)
def list_sync_runs(
    session: DbSession,
    settings: AppSettings,
    _admin: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> Page[SyncRunRead]:
    runs, total = JobSyncService(session, settings).list_runs(page=page, page_size=page_size)
    return Page(
        data=[sync_run_to_read(run) for run in runs],
        meta=PageMeta(page=page, page_size=page_size, total=total),
    )


@router.get(
    "/{run_id}",
    response_model=DataResponse[SyncRunRead],
    summary="单个同步任务状态",
)
def get_sync_run(
    run_id: UUID,
    session: DbSession,
    settings: AppSettings,
    _admin: AdminUser,
) -> DataResponse[SyncRunRead]:
    run = JobSyncService(session, settings).get_run(run_id)
    return DataResponse(data=sync_run_to_read(run))
