"""Candidate leads: discovery, private manual imports and official verification."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.schemas.leads import (
    JobLeadDetail,
    JobLeadRead,
    LeadImportRequest,
    LeadVerificationResult,
    LeadVerifyBatchRequest,
    LeadVerifyBatchResult,
    OfficialSourceRead,
    TrustedTenantRead,
    lead_to_read,
)
from app.search.source_catalog import official_sources
from app.security.csrf import require_csrf
from app.services.job_discovery_service import JobDiscoveryService
from app.services.job_lead_service import JobLeadService
from app.services.job_maintenance_service import JobMaintenanceService

router = APIRouter(prefix="/job-leads", tags=["job-leads"], dependencies=[Depends(require_csrf)])


@router.get(
    "",
    response_model=DataResponse[list[JobLeadRead]],
    summary="公开候选链接 + 当前用户私有导入",
)
def list_leads(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
    company: str | None = Query(default=None, max_length=50),
) -> DataResponse[list[JobLeadRead]]:
    leads = JobDiscoveryService(session, settings).list_leads(user.id, query=query, company=company)
    return DataResponse(data=leads)


@router.get(
    "/sources",
    response_model=DataResponse[list[OfficialSourceRead]],
    summary="已在线校验的官方招聘来源目录",
)
def list_official_sources(user: CurrentUser) -> DataResponse[list[OfficialSourceRead]]:
    return DataResponse(
        data=[
            OfficialSourceRead(
                company=source.company,
                name=source.name,
                domains=list(source.domains),
                priority=source.priority,
                http_status=source.http_status,
                final_url=source.final_url,
                verified_at=source.verified_at,
                detail_verification=source.detail_verification,
                note=source.note,
                official_entrypoints=list(source.official_entrypoints),
                trusted_tenants=[
                    TrustedTenantRead(
                        provider=tenant.provider,
                        host=tenant.host,
                        path_prefix=tenant.path_prefix,
                        entry_url=tenant.entry_url,
                        evidence_url=tenant.evidence_url,
                        verified_at=tenant.verified_at,
                    )
                    for tenant in source.trusted_tenants
                ],
                search_domains=list(source.search_domains),
                job_url_patterns=list(source.job_url_patterns),
                verification_status=source.verification_status,
                access_policy=source.access_policy,
            )
            for source in official_sources()
        ]
    )


@router.post(
    "/import",
    response_model=DataResponse[JobLeadRead],
    status_code=status.HTTP_201_CREATED,
    summary="导入官方链接及可选 JD（默认仅本人可见）",
)
def import_lead(
    payload: LeadImportRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[JobLeadRead]:
    lead = JobLeadService(session, settings).import_private(
        user_id=user.id,
        url=str(payload.url),
        title=payload.title,
        description=payload.description,
        city=payload.city,
        job_type=payload.job_type,
        published_date=payload.published_date,
        company=payload.company,
    )
    return DataResponse(data=lead_to_read(lead))


@router.post(
    "/verify-batch",
    response_model=DataResponse[LeadVerifyBatchResult],
    summary="批量核验候选岗位（单条失败不影响其他）",
)
def verify_leads_batch(
    payload: LeadVerifyBatchRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[LeadVerifyBatchResult]:
    data = JobLeadService(session, settings).verify_many(payload.lead_ids, user.id)
    return DataResponse(data=LeadVerifyBatchResult(**data))


@router.get(
    "/pending-count",
    response_model=DataResponse[dict],
    summary="所选企业待核验的候选数量（用于按钮文案）",
)
def pending_lead_count(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    companies: str | None = Query(default=None, description="逗号分隔的企业名"),
) -> DataResponse[dict]:
    names = [item.strip() for item in (companies or "").split(",") if item.strip()]
    count = JobMaintenanceService(session, settings).pending_lead_count(user.id, names)
    return DataResponse(data={"count": count})


@router.get(
    "/{lead_id}",
    response_model=DataResponse[JobLeadDetail],
    summary="候选岗位详情与来源证据",
)
def get_lead(
    lead_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[JobLeadDetail]:
    service = JobLeadService(session, settings)
    lead = service.get_for_user(lead_id, user.id)
    return DataResponse(
        data=JobLeadDetail(
            lead=lead_to_read(lead),
            evidence=service.evidence_for_lead(lead.id),
        )
    )


@router.post(
    "/{lead_id}/verify",
    response_model=DataResponse[LeadVerificationResult],
    summary="对允许的官方公开详情页执行核验",
)
def verify_lead(
    lead_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[LeadVerificationResult]:
    lead, outcome = JobLeadService(session, settings).verify(lead_id, user.id)
    if lead.job_id is None:  # pragma: no cover - service guarantees it
        raise RuntimeError("verified lead missing job")
    return DataResponse(
        data=LeadVerificationResult(
            lead=lead_to_read(lead),
            job_id=lead.job_id,
            created=outcome.created,
            updated=outcome.updated,
        )
    )
