"""Saved job and to-apply list endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.db.models.enums import SavedListType
from app.schemas.common import DataResponse, Page, PageMeta
from app.schemas.saved_jobs import SavedJobRead, SaveJobRequest, saved_job_to_read
from app.security.csrf import require_csrf
from app.services.saved_job_service import SavedJobService

router = APIRouter(tags=["saved-jobs"], dependencies=[Depends(require_csrf)])


@router.post(
    "/jobs/{job_id}/save",
    response_model=DataResponse[SavedJobRead],
    summary="收藏岗位或加入待投递清单（按 list_type 幂等）",
)
def save_job(
    job_id: UUID,
    payload: SaveJobRequest,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[SavedJobRead]:
    row, created = SavedJobService(session, settings).save(
        user, job_id, payload.list_type, payload.note
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return DataResponse(data=saved_job_to_read(row))


@router.delete(
    "/jobs/{job_id}/save",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="取消收藏（幂等，按 list_type 指定清单）",
)
def unsave_job(
    job_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    list_type: SavedListType = Query(default=SavedListType.SAVED),
) -> Response:
    SavedJobService(session, settings).remove(user, job_id, list_type)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/saved-jobs",
    response_model=Page[SavedJobRead],
    summary="收藏与待投递清单",
)
def list_saved_jobs(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    list_type: SavedListType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> Page[SavedJobRead]:
    rows, total = SavedJobService(session, settings).list(
        user, list_type=list_type, page=page, page_size=page_size
    )
    return Page(
        data=[saved_job_to_read(row) for row in rows],
        meta=PageMeta(page=page, page_size=page_size, total=total),
    )
