"""Job library maintenance: refresh existing postings, discover new, prune closed.

Archiving touches a shared library, so prune/preview/restore require an admin
(``ADMIN_EMAILS``) even on a single-user deployment.
"""

from __future__ import annotations

from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.auth.dependencies import AdminUser, AppSettings, CurrentUser, DbSession
from app.core.errors import AppError
from app.schemas.common import DataResponse
from app.schemas.job_maintenance import (
    MaintenanceAccepted,
    MaintenanceCreate,
    MaintenanceRunRead,
    MaintenanceScope,
    PrunePreview,
    PrunePreviewItem,
    maintenance_to_read,
)
from app.security.csrf import require_csrf
from app.services.job_maintenance_service import JobMaintenanceService

router = APIRouter(
    prefix="/job-maintenance",
    tags=["job-maintenance"],
    dependencies=[Depends(require_csrf)],
)


def _dispatch(run_id: UUID, *, kind: str, recheck: bool, discover: bool) -> None:
    """Enqueue after the row is committed; a broker hiccup must not 500."""
    from app.workers.tasks import job_prune, job_refresh

    with suppress(Exception):
        if kind == "prune":
            job_prune.delay(str(run_id))
        else:
            job_refresh.delay(str(run_id), recheck, discover)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DataResponse[MaintenanceAccepted],
    summary="更新岗位（复核已有 / 发现新增）",
)
def create_refresh(
    payload: MaintenanceCreate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[MaintenanceAccepted]:
    if payload.kind == "prune":
        raise AppError("INVALID_KIND", "清理已下线请使用 /job-maintenance/prune", status_code=422)
    if not (payload.recheck or payload.discover):
        raise AppError(
            "INVALID_OPTIONS",
            "至少选择一项：复核已有岗位或发现新增岗位",
            status_code=422,
        )
    service = JobMaintenanceService(session, settings)
    run, created = service.create_run(
        user,
        kind=payload.kind,
        scope=payload.scope.model_dump(),
        options={
            "recheck": payload.recheck,
            "discover": payload.discover,
            "max_jobs": payload.max_jobs,
            "cooldown_hours": payload.cooldown_hours,
        },
    )
    if created:
        _dispatch(run.id, kind=payload.kind, recheck=payload.recheck, discover=payload.discover)
    return DataResponse(
        data=MaintenanceAccepted(run_id=run.id, status=run.status, reused=not created)
    )


@router.post(
    "/prune",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DataResponse[MaintenanceAccepted],
    summary="清理已下线（管理员，软归档）",
)
def create_prune(
    payload: MaintenanceCreate,
    session: DbSession,
    settings: AppSettings,
    admin: AdminUser,
) -> DataResponse[MaintenanceAccepted]:
    service = JobMaintenanceService(session, settings)
    run, created = service.create_run(
        admin,
        kind="prune",
        scope=payload.scope.model_dump(),
        options={},
    )
    if created:
        _dispatch(run.id, kind="prune", recheck=False, discover=False)
    return DataResponse(
        data=MaintenanceAccepted(run_id=run.id, status=run.status, reused=not created)
    )


@router.get(
    "/prune-preview",
    response_model=DataResponse[PrunePreview],
    summary="清理预览（管理员）：只列出有明确下线证据的岗位",
)
def prune_preview(
    session: DbSession,
    settings: AppSettings,
    admin: AdminUser,
    q: str | None = None,
    companies: str | None = None,
    cities: str | None = None,
    job_types: str | None = None,
) -> DataResponse[PrunePreview]:
    from app.core.text import split_csv

    scope = MaintenanceScope(
        q=q,
        companies=split_csv(companies),
        cities=split_csv(cities),
        job_types=split_csv(job_types),
    ).model_dump()
    preview = JobMaintenanceService(session, settings).prune_preview(scope)
    return DataResponse(
        data=PrunePreview(
            count=preview["count"],
            items=[PrunePreviewItem(**item) for item in preview["items"]],
            truncated=preview["truncated"],
        )
    )


@router.get(
    "/{run_id}",
    response_model=DataResponse[MaintenanceRunRead],
    summary="维护任务进度与结果",
)
def get_maintenance(
    run_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[MaintenanceRunRead]:
    service = JobMaintenanceService(session, settings)
    run = service.get_run(run_id)
    if run.user_id != user.id and user.email.strip().lower() not in settings.admin_email_set:
        raise AppError("MAINTENANCE_NOT_FOUND", "任务不存在", status_code=404)
    return DataResponse(data=maintenance_to_read(run))


@router.post(
    "/{run_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="请求取消维护任务（协作式，批次边界生效）",
)
def cancel_maintenance(
    run_id: UUID,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> Response:
    service = JobMaintenanceService(session, settings)
    run = service.get_run(run_id)
    if run.user_id != user.id and user.email.strip().lower() not in settings.admin_email_set:
        raise AppError("MAINTENANCE_NOT_FOUND", "任务不存在", status_code=404)
    service.cancel(run_id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/jobs/{job_id}/restore",
    response_model=DataResponse[dict],
    summary="恢复归档岗位（管理员，仅取消归档，不代表恢复在招）",
)
def restore_job(
    job_id: UUID,
    session: DbSession,
    settings: AppSettings,
    admin: AdminUser,
) -> DataResponse[dict]:
    service = JobMaintenanceService(session, settings)
    job = service.get_job(job_id)
    if job.archived_at is None:
        raise AppError("JOB_NOT_ARCHIVED", "该岗位未被归档", status_code=409)
    return DataResponse(data=service.restore(job, admin.id))
