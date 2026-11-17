"""Job source registry and health endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.dependencies import AdminUser, AppSettings, CurrentUser, DbSession
from app.connectors.errors import ConnectorError
from app.connectors.registry import build_connector
from app.schemas.common import DataResponse
from app.schemas.sources import (
    ConnectorHealthRead,
    JobSourceRead,
    JobSourceUpdate,
    source_to_read,
)
from app.security.csrf import require_csrf
from app.services.job_sync_service import JobSyncService

router = APIRouter(
    prefix="/job-sources", tags=["job-sources"], dependencies=[Depends(require_csrf)]
)


@router.get(
    "",
    response_model=DataResponse[list[JobSourceRead]],
    summary="数据源列表与最近同步状态",
)
def list_job_sources(
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
) -> DataResponse[list[JobSourceRead]]:
    sources = JobSyncService(session, settings).list_sources()
    return DataResponse(data=[source_to_read(source) for source in sources])


@router.get(
    "/{source_id}",
    response_model=DataResponse[JobSourceRead],
    summary="数据源详情",
)
def get_job_source(
    source_id: UUID,
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
) -> DataResponse[JobSourceRead]:
    source = JobSyncService(session, settings).get_source(source_id)
    return DataResponse(data=source_to_read(source))


@router.patch(
    "/{source_id}",
    response_model=DataResponse[JobSourceRead],
    summary="管理员更新数据源启用状态与安全配置",
)
def update_job_source(
    source_id: UUID,
    payload: JobSourceUpdate,
    session: DbSession,
    settings: AppSettings,
    _admin: AdminUser,
) -> DataResponse[JobSourceRead]:
    source = JobSyncService(session, settings).update_source(
        source_id, enabled=payload.enabled, config=payload.config
    )
    return DataResponse(data=source_to_read(source))


@router.get(
    "/{source_id}/health",
    response_model=DataResponse[ConnectorHealthRead],
    summary="数据源连接器健康检查（不触发同步）",
)
def get_source_health(
    source_id: UUID,
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
) -> DataResponse[ConnectorHealthRead]:
    source = JobSyncService(session, settings).get_source(source_id)
    try:
        health = build_connector(source.source_type, settings).health_check(source.config_json)
    except ConnectorError as exc:
        return DataResponse(
            data=ConnectorHealthRead(
                configured=False,
                ok=False,
                message=exc.message,
                checked_at=datetime.now(UTC),
            )
        )
    return DataResponse(
        data=ConnectorHealthRead(
            configured=health.configured,
            ok=health.ok,
            message=health.message,
            checked_at=health.checked_at,
        )
    )
