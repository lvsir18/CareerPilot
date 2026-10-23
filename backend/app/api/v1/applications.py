"""Manual application tracking endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.db.models.enums import ApplicationStatus
from app.schemas.applications import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationEventCreate,
    ApplicationEventRead,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
    application_to_read,
    event_to_read,
)
from app.schemas.common import DataResponse, Page, PageMeta
from app.security.csrf import require_csrf
from app.services.application_service import ApplicationService

router = APIRouter(
    prefix="/applications", tags=["applications"], dependencies=[Depends(require_csrf)]
)


@router.post(
    "",
    response_model=DataResponse[ApplicationRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建本系统内的投递记录（不会向外部网站提交）",
)
def create_application(
    payload: ApplicationCreate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ApplicationRead]:
    application = ApplicationService(session, settings).create(
        user,
        job_id=payload.job_id,
        job_lead_id=payload.job_lead_id,
        external_company=payload.external_company,
        external_title=payload.external_title,
        external_url=str(payload.external_url) if payload.external_url else None,
        status=payload.status,
        notes=payload.notes,
        applied_at=payload.applied_at,
    )
    return DataResponse(data=application_to_read(application))


@router.get(
    "",
    response_model=Page[ApplicationRead],
    summary="投递看板列表",
)
def list_applications(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    company: str | None = Query(default=None, max_length=200),
    query: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> Page[ApplicationRead]:
    rows, total = ApplicationService(session, settings).list(
        user,
        status=status_filter,
        company=company,
        query=query,
        page=page,
        page_size=page_size,
    )
    return Page(
        data=[application_to_read(row) for row in rows],
        meta=PageMeta(page=page, page_size=page_size, total=total),
    )


@router.get(
    "/{application_id}",
    response_model=DataResponse[ApplicationDetail],
    summary="投递详情（含状态时间线）",
)
def get_application(
    application_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ApplicationDetail]:
    application = ApplicationService(session, settings).get(user, application_id)
    detail = ApplicationDetail(
        **application_to_read(application).model_dump(),
        events=[event_to_read(event) for event in application.events],
    )
    return DataResponse(data=detail)


@router.patch(
    "/{application_id}",
    response_model=DataResponse[ApplicationRead],
    summary="更新申请备注与外部岗位信息（状态时间线不改写）",
)
def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ApplicationRead]:
    application = ApplicationService(session, settings).update_metadata(
        user,
        application_id,
        notes=payload.notes,
        external_company=payload.external_company,
        external_title=payload.external_title,
        external_url=str(payload.external_url) if payload.external_url else None,
    )
    return DataResponse(data=application_to_read(application))


@router.get(
    "/{application_id}/events",
    response_model=DataResponse[list[ApplicationEventRead]],
    summary="投递状态时间线",
)
def list_application_events(
    application_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[list[ApplicationEventRead]]:
    events = ApplicationService(session, settings).events(user, application_id)
    return DataResponse(data=[event_to_read(event) for event in events])


@router.post(
    "/{application_id}/events",
    response_model=DataResponse[ApplicationEventRead],
    status_code=status.HTTP_201_CREATED,
    summary="追加用户确认的进度事件（可纠正状态，保留历史）",
)
def add_application_event(
    application_id: UUID,
    payload: ApplicationEventCreate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ApplicationEventRead]:
    event = ApplicationService(session, settings).add_event(
        user,
        application_id,
        status=payload.status,
        event_time=payload.event_time,
        note=payload.note,
        evidence_summary=payload.evidence_summary,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        verification_status=payload.verification_status,
    )
    return DataResponse(data=event_to_read(event))


@router.patch(
    "/{application_id}/status",
    response_model=DataResponse[ApplicationRead],
    summary="手动更新投递状态并追加事件",
)
def update_application_status(
    application_id: UUID,
    payload: ApplicationStatusUpdate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ApplicationRead]:
    application = ApplicationService(session, settings).update_status(
        user,
        application_id,
        status=payload.status,
        note=payload.note,
        applied_at=payload.applied_at,
    )
    return DataResponse(data=application_to_read(application))


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除投递记录（同时删除事件历史）",
)
def delete_application(
    application_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> Response:
    ApplicationService(session, settings).delete(user, application_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
