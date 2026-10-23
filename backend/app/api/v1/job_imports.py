"""User-initiated public-page job imports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.schemas.imports import ImportPreview, ImportPreviewRequest, JobImportRequest
from app.schemas.jobs import JobDetail, job_to_detail
from app.security.csrf import require_csrf
from app.services.job_import_service import JobImportService

router = APIRouter(
    prefix="/job-imports", tags=["job-imports"], dependencies=[Depends(require_csrf)]
)


@router.post(
    "/preview",
    response_model=DataResponse[ImportPreview],
    summary="预览官方链接解析结果（不写库）",
)
def preview_import(
    payload: ImportPreviewRequest,
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
) -> DataResponse[ImportPreview]:
    preview = JobImportService(session, settings).preview(str(payload.url))
    return DataResponse(data=preview)


@router.post(
    "",
    response_model=DataResponse[JobDetail],
    status_code=status.HTTP_201_CREATED,
    summary="确认导入岗位（官方页面解析或用户粘贴）",
)
def import_job(
    payload: JobImportRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[JobDetail]:
    job, _outcome = JobImportService(session, settings).import_job(payload, user.id)
    return DataResponse(data=job_to_detail(job))


@router.get(
    "/capabilities",
    response_model=DataResponse[dict[str, object]],
    summary="当前支持的导入方式",
)
def import_capabilities(_user: CurrentUser) -> DataResponse[dict[str, object]]:
    return DataResponse(
        data={
            "public_page": {
                "providers": ["baidu"],
                "domains": ["talent.baidu.com"],
                "mode": "single_user_submitted_url",
                "bulk_sync": False,
            },
            "manual_paste": {"supported": True, "verification": "user_confirmed"},
            "manual_import": {"supported": True, "verification": "unverified"},
        }
    )
