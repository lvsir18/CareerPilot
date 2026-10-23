"""Job listing and detail endpoints (read-only by design)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.core.errors import AppError
from app.core.text import split_csv
from app.db.models.enums import JobStatus
from app.repositories.jobs import JobQuery
from app.schemas.common import DataResponse, Page, PageMeta
from app.schemas.jobs import JobDetail, JobListItem, JobSort, job_to_detail, job_to_list_item
from app.schemas.leads import DiscoveryResponse
from app.security.csrf import require_csrf
from app.services.job_discovery_service import JobDiscoveryService
from app.services.job_lead_service import JobLeadService
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_csrf)])


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@router.get(
    "",
    response_model=Page[JobListItem],
    summary="岗位搜索（关键词、公司、城市、类型、来源、时间、分页）",
)
def list_jobs(
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
    q: str | None = Query(default=None, max_length=200, description="标题 / 公司 / JD 关键词"),
    keyword: str | None = Query(default=None, max_length=200, description="q 的兼容别名（q 优先）"),
    companies: str | None = Query(default=None, description="逗号分隔的公司名"),
    cities: str | None = Query(default=None, description="逗号分隔的城市"),
    job_types: str | None = Query(default=None, description="逗号分隔，如 internship,campus"),
    source_types: str | None = Query(default=None, description="逗号分隔的数据源类型"),
    recruitment_program: str | None = Query(
        default=None, description="逗号分隔的招聘项目，如 2027届秋招"
    ),
    is_demo: bool | None = Query(default=None, description="仅筛演示/真实岗位"),
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    published_date_known: bool | None = Query(
        default=None, description="true 仅返回有可核验发布时间的岗位"
    ),
    status: JobStatus | None = None,
    sort: JobSort = "published_at_desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> Page[JobListItem]:
    after = _as_utc(published_after)
    before = _as_utc(published_before)
    if after is not None and before is not None and after > before:
        raise AppError(
            code="INVALID_DATE_RANGE",
            message="published_after 不能晚于 published_before",
            status_code=422,
        )

    jobs, total = JobService(session, settings).list_jobs(
        JobQuery(
            q=q or keyword,
            companies=split_csv(companies),
            cities=split_csv(cities),
            job_types=split_csv(job_types),
            source_types=split_csv(source_types),
            recruitment_programs=split_csv(recruitment_program),
            is_demo=is_demo,
            published_after=after,
            published_before=before,
            published_date_known=published_date_known,
            status=status,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    )
    return Page(
        data=[job_to_list_item(job) for job in jobs],
        meta=PageMeta(page=page, page_size=page_size, total=total),
    )


@router.get(
    "/discover",
    response_model=DataResponse[DiscoveryResponse],
    summary="联邦发现：已有岗位 + 官方候选链接",
)
def discover_jobs(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
    company: str | None = Query(default=None, max_length=50),
    companies: str | None = Query(default=None, description="逗号分隔的企业"),
    city: str | None = Query(default=None, max_length=50),
    job_type: str | None = Query(default=None, max_length=50),
    job_family: str | None = Query(
        default=None,
        max_length=50,
        description=(
            "llm_agent / algorithm_data / backend / frontend / product / "
            "design / operations / other"
        ),
    ),
    verification: str = Query(default="all", pattern="^(all|verified|pending)$"),
    published_within_days: int | None = Query(default=None, ge=1, le=365),
    days: int | None = Query(default=None, ge=1, le=365),
    sort: str = Query(default="relevance", pattern="^(relevance|newest|published)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    limit: int | None = Query(default=None, ge=1, le=50, description="page_size 的兼容别名"),
) -> DataResponse[DiscoveryResponse]:
    service = JobDiscoveryService(session, settings)
    try:
        result = service.discover(
            user.id,
            query=query,
            companies=split_csv(companies),
            company=company,
            city=city,
            job_type=job_type,
            job_family=job_family,
            verification=verification,
            published_within_days=published_within_days,
            days=days,
            sort=sort,
            page=page,
            page_size=limit or page_size,
        )
    finally:
        service.close()
    return DataResponse(data=result)


@router.get(
    "/{job_id}",
    response_model=DataResponse[JobDetail],
    summary="岗位详情（含原始 JD 与来源）",
)
def get_job(
    job_id: UUID,
    session: DbSession,
    settings: AppSettings,
    _user: CurrentUser,
) -> DataResponse[JobDetail]:
    job = JobService(session, settings).get_job(job_id)
    evidence = JobLeadService(session, settings).evidence_for_job(job.id)
    return DataResponse(data=job_to_detail(job, evidence))
