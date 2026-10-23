"""Tencent campus recruiting import (official public JSON API)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.connectors.tencent_campus import DEFAULT_PROJECT, PROJECTS
from app.schemas.common import DataResponse
from app.security.csrf import require_csrf
from app.services.tencent_campus_service import TencentCampusService

router = APIRouter(prefix="/tencent", tags=["tencent"], dependencies=[Depends(require_csrf)])


class TencentImportRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=30, description="岗位关键词，如 算法")
    project: str = Field(default=DEFAULT_PROJECT, description="招聘项目，如 日常实习")
    limit: int = Field(default=10, ge=1, le=20, description="最多导入条数")


@router.get(
    "/projects",
    response_model=DataResponse[dict[str, Any]],
    summary="腾讯校招可选的招聘项目（日常实习/应届实习/应届毕业生/青云计划）",
)
def list_projects(_user: CurrentUser) -> DataResponse[dict[str, Any]]:
    return DataResponse(
        data={
            "default": DEFAULT_PROJECT,
            "projects": [{"name": name, "id": project_id} for name, project_id in PROJECTS.items()],
            "job_type_map": {
                "日常实习": "internship",
                "应届实习": "internship",
                "青云计划-实习生": "internship",
                "应届毕业生": "campus",
                "青云计划-应届生": "campus",
            },
        }
    )


@router.post(
    "/jobs/import",
    response_model=DataResponse[dict[str, Any]],
    summary="从腾讯校招官方接口导入岗位（含完整 JD 与招聘类型）",
)
def import_tencent_jobs(
    payload: TencentImportRequest,
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
) -> DataResponse[dict[str, Any]]:
    result = TencentCampusService(session, settings).import_jobs(
        keyword=payload.keyword,
        project=payload.project,
        limit=payload.limit,
    )
    return DataResponse(data=result)
