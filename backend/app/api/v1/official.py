"""Official-source job search endpoints (API route + rendered route)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.security.csrf import require_csrf
from app.services.official_jobs_service import (
    OfficialJobsService,
    supported_sources,
)

router = APIRouter(prefix="/official", tags=["official"], dependencies=[Depends(require_csrf)])


class OfficialSearchRequest(BaseModel):
    companies: Annotated[list[str], Field(min_length=1, max_length=6)]
    keyword: str | None = Field(default=None, max_length=30)
    limit: int = Field(default=5, ge=1, le=10, description="每家公司最多返回条数")
    project: str | None = Field(
        default=None, max_length=20, description="腾讯招聘项目；其他企业忽略"
    )


@router.get(
    "/sources",
    response_model=DataResponse[list[dict[str, Any]]],
    summary="支持官方直连的企业（腾讯走 JSON 接口，其余走浏览器渲染官方搜索页）",
)
def list_sources(_user: CurrentUser) -> DataResponse[list[dict[str, Any]]]:
    return DataResponse(data=supported_sources())


@router.post(
    "/jobs/search",
    response_model=DataResponse[dict[str, Any]],
    summary="从企业官方招聘页直接检索岗位（含完整 JD 与招聘类型）",
)
def search_official_jobs(
    payload: OfficialSearchRequest,
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
) -> DataResponse[dict[str, Any]]:
    service = OfficialJobsService(session, settings)
    result = service.search(
        companies=payload.companies,
        keyword=payload.keyword,
        limit=payload.limit,
        project=payload.project,
    )
    return DataResponse(data=result)
