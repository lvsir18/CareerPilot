"""Job matching and recommendation endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.core.text import split_csv
from app.schemas.common import DataResponse, Page, PageMeta
from app.schemas.matching import MatchResultRead, RecommendationItem
from app.security.csrf import require_csrf
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/matches", tags=["matches"], dependencies=[Depends(require_csrf)])


@router.post(
    "/jobs/{job_id}",
    response_model=DataResponse[RecommendationItem],
    summary="对单个已核验岗位执行完整匹配",
)
def match_job(
    job_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[RecommendationItem]:
    item = RecommendationService(session, settings).match_job(user, job_id)
    return DataResponse(data=item)


@router.post(
    "/job-leads/{lead_id}",
    response_model=DataResponse[MatchResultRead],
    summary="对搜索候选 JobLead 执行基础匹配（不输出完整技能评分）",
)
def match_job_lead(
    lead_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[MatchResultRead]:
    result = RecommendationService(session, settings).match_lead(user, lead_id)
    return DataResponse(data=result)


@router.get(
    "/recommendations",
    response_model=Page[RecommendationItem],
    summary="个性化岗位推荐（仅完整 JD 岗位，支持过滤与排除已申请）",
)
def recommendations(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    companies: str | None = Query(default=None, description="逗号分隔的公司名"),
    cities: str | None = Query(default=None, description="逗号分隔的城市"),
    job_types: str | None = Query(default=None, description="逗号分隔，如 internship,campus"),
    exclude_applied: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> Page[RecommendationItem]:
    items, total = RecommendationService(session, settings).recommendations(
        user,
        companies=split_csv(companies),
        cities=split_csv(cities),
        job_types=split_csv(job_types),
        exclude_applied=exclude_applied,
        page=page,
        page_size=page_size,
    )
    return Page(
        data=items,
        meta=PageMeta(page=page, page_size=page_size, total=total),
    )
