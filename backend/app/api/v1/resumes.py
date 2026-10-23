"""Resume upload, listing, detail and deletion endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.schemas.resumes import ResumeRead, resume_to_read
from app.security.csrf import require_csrf
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/resumes", tags=["resumes"], dependencies=[Depends(require_csrf)])


@router.post(
    "",
    response_model=DataResponse[ResumeRead],
    status_code=status.HTTP_201_CREATED,
    summary="上传 PDF/DOCX 简历并解析",
)
async def upload_resume(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> DataResponse[ResumeRead]:
    raw = await file.read()
    resume = ResumeService(session, settings).upload(
        user,
        filename=file.filename or "resume",
        raw=raw,
        content_type=file.content_type,
    )
    return DataResponse(data=resume_to_read(resume))


@router.get(
    "",
    response_model=DataResponse[list[ResumeRead]],
    summary="当前用户的简历列表",
)
def list_resumes(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=50),
) -> DataResponse[list[ResumeRead]]:
    rows = ResumeService(session, settings).list(user, limit=limit)
    return DataResponse(data=[resume_to_read(row) for row in rows])


@router.get(
    "/{resume_id}",
    response_model=DataResponse[ResumeRead],
    summary="简历详情与解析结果",
)
def get_resume(
    resume_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ResumeRead]:
    row = ResumeService(session, settings).get(user, resume_id)
    return DataResponse(data=resume_to_read(row))


@router.delete(
    "/{resume_id}",
    response_model=DataResponse[None],
    summary="删除简历及原始文件",
)
def delete_resume(
    resume_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[None]:
    ResumeService(session, settings).delete(user, resume_id)
    return DataResponse(data=None)


@router.post(
    "/{resume_id}/primary",
    response_model=DataResponse[ResumeRead],
    summary="将某份简历设为画像主要来源",
)
def set_primary_resume(
    resume_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ResumeRead]:
    row = ResumeService(session, settings).set_primary(user, resume_id)
    return DataResponse(data=resume_to_read(row))
