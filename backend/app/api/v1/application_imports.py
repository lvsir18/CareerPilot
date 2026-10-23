"""User-owned .eml progress import preview and confirmation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.schemas.progress_imports import ApplicationImportConfirm, ApplicationImportRead
from app.security.csrf import require_csrf
from app.services.application_import_service import (
    MAX_EMAIL_BYTES,
    ApplicationImportService,
    import_to_read,
)

router = APIRouter(
    prefix="/application-imports",
    tags=["application-imports"],
    dependencies=[Depends(require_csrf)],
)


@router.post(
    "/email",
    response_model=DataResponse[ApplicationImportRead],
    status_code=status.HTTP_201_CREATED,
    summary="上传 .eml 招聘通知并生成预览（不自动更新进度）",
)
async def import_email(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> DataResponse[ApplicationImportRead]:
    filename = file.filename or "upload.eml"
    raw = await file.read(MAX_EMAIL_BYTES + 1)
    row, duplicate = ApplicationImportService(session, settings).import_email(
        user,
        filename=filename,
        raw=raw,
    )
    return DataResponse(data=import_to_read(row, duplicate=duplicate))


@router.get(
    "",
    response_model=DataResponse[list[ApplicationImportRead]],
    summary="当前用户的邮件导入记录（脱敏摘要）",
)
def list_imports(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=50),
) -> DataResponse[list[ApplicationImportRead]]:
    rows = ApplicationImportService(session, settings).list_for_user(user.id, limit=limit)
    return DataResponse(data=[import_to_read(row) for row in rows])


@router.get(
    "/{import_id}",
    response_model=DataResponse[ApplicationImportRead],
    summary="邮件导入预览详情",
)
def get_import(
    import_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ApplicationImportRead]:
    row = ApplicationImportService(session, settings).get(user.id, import_id)
    return DataResponse(data=import_to_read(row))


@router.post(
    "/{import_id}/confirm",
    response_model=DataResponse[ApplicationImportRead],
    summary="用户确认后写入申请进度事件（幂等）",
)
def confirm_import(
    import_id: UUID,
    payload: ApplicationImportConfirm,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ApplicationImportRead]:
    row = ApplicationImportService(session, settings).confirm(
        user,
        import_id,
        application_id=payload.application_id,
        status=payload.status,
        event_time=payload.event_time,
        note=payload.note,
    )
    return DataResponse(data=import_to_read(row))
