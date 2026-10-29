"""Federated discovery: official search leads + verified local jobs."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.repositories.jobs import JobQuery
from app.schemas.jobs import job_to_list_item
from app.schemas.leads import (
    CompanySearchDiagnosticRead,
    DiscoveryResponse,
    JobLeadRead,
    ProviderResultRead,
    ProviderStatusRead,
    SearchStatusRead,
    lead_to_read,
)
from app.search.base import SearchOutcome
from app.search.domains import COMPANY_NAMES, resolve_company
from app.search.service import SearchService
from app.search.taxonomy import classify_job_family, is_known_family, job_family_matches
from app.services.job_lead_service import JobLeadService
from app.services.job_service import JobService

DISCOVERY_SORTS = ("relevance", "newest", "published")


class JobDiscoveryService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        search_service: SearchService | None = None,
        lead_service: JobLeadService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._search = search_service or SearchService(settings)
        self._leads = lead_service or JobLeadService(session, settings)

    def _resolve_companies(
        self, companies: list[str] | None, company: str | None
    ) -> tuple[list[str], list[str]]:
        """Return ``(resolved_keys, unknown_values)``.

        Agent tools routinely pass a company name that has no configured
        official domain ("阿里巴巴达摩院"). Failing the whole search for one
        unknown name turned a usable answer into ``partial``; the caller now
        skips it and reports it as a warning instead.
        """
        requested = list(companies or [])
        if company:
            requested.append(company)
        if not requested:
            return [], []
        resolved: list[str] = []
        unknown: list[str] = []
        for value in requested:
            key = resolve_company(value)
            if key is None:
                unknown.append(str(value))
                continue
            if key not in resolved:
                resolved.append(key)
        if not resolved:
            raise AppError(
                code="INVALID_COMPANY",
                message="暂不支持该企业，仅支持已配置的官方招聘域名",
                status_code=422,
            )
        return resolved, unknown

    def discover(
        self,
        user_id: UUID,
        *,
        query: str | None,
        companies: list[str] | None = None,
        company: str | None = None,
        city: str | None = None,
        job_type: str | None = None,
        job_family: str | None = None,
        verification: str = "all",
        published_within_days: int | None = None,
        days: int | None = None,
        sort: str = "relevance",
        page: int = 1,
        page_size: int = 20,
        prefer_local: bool = False,
    ) -> DiscoveryResponse:
        selected, unknown_companies = self._resolve_companies(companies, company)
        if job_family and not is_known_family(job_family):
            raise AppError(
                code="INVALID_JOB_FAMILY",
                message="不支持的岗位方向",
                status_code=422,
            )
        if sort not in DISCOVERY_SORTS:
            raise AppError(
                code="INVALID_SORT",
                message="不支持的排序方式",
                status_code=422,
            )
        if verification not in {"all", "verified", "pending"}:
            raise AppError(
                code="INVALID_VERIFICATION_FILTER",
                message="不支持的核验状态",
                status_code=422,
            )
        page = max(1, page)
        page_size = min(max(page_size, 1), 50)
        search_limit = min(page_size * page, 50)

        jobs, _job_total = self._local_jobs(
            query,
            selected,
            city,
            job_type,
            job_family,
            days,
            sort,
            published_within_days,
            verification,
        )
        # The library usually already answers an agent ask, and one live search
        # fans out to ~20 Tavily queries. Skipping it keeps a single run from
        # draining the whole daily budget (which then rejects later searches).
        if prefer_local and jobs:
            outcome = SearchOutcome(
                hits=[],
                providers_used=[],
                configured=True,
                licensed_configured=False,
                warnings=["岗位库已有命中，本轮跳过实时检索"],
            )
        else:
            outcome = self._search.search(
                query or "",
                company_keys=selected,
                city=city,
                job_type=job_type,
                job_family=job_family,
                limit=search_limit,
                user_id=user_id,
            )
        warnings = list(outcome.warnings)
        if unknown_companies:
            warnings.append(f"已忽略无法识别的企业：{'、'.join(unknown_companies)}")
        for hit in outcome.hits:
            try:
                self._leads.upsert_search_hit(hit)
            except AppError as exc:
                warnings.append(f"忽略无效搜索结果：{exc.message}")
            except Exception:
                warnings.append("忽略一条无法标准化的搜索结果")
        self._session.commit()

        lead_sort = "published" if sort == "published" else "relevance"
        all_leads = self._leads.list_for_user(
            user_id,
            query=query,
            companies=selected,
            job_family=job_family,
            days=days,
            limit=500,
            sort=lead_sort,
        )
        if verification == "verified":
            all_leads = [
                lead for lead in all_leads if lead.verification_status == "verified_official"
            ]
        elif verification == "pending":
            all_leads = [
                lead for lead in all_leads if lead.verification_status != "verified_official"
            ]
        if published_within_days:
            from datetime import date, timedelta

            cutoff_date = date.today() - timedelta(days=published_within_days)
            all_leads = [
                lead
                for lead in all_leads
                if lead.published_date is not None and lead.published_date >= cutoff_date
            ]
        offset = (page - 1) * page_size
        page_leads = all_leads[offset : offset + page_size]
        page_jobs = jobs[offset : offset + page_size]
        total_leads = len(all_leads)
        # ``job_total`` counts DB-level filters; post-classification may reduce it.
        total_jobs = len(jobs)
        total_pages = max(1, math.ceil(max(total_leads, total_jobs) / page_size))

        return DiscoveryResponse(
            query=query,
            companies=selected,
            job_family=job_family,
            sort=sort,
            verification=verification,
            published_within_days=published_within_days,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            jobs=[job_to_list_item(job) for job in page_jobs],
            leads=[lead_to_read(lead) for lead in page_leads],
            search=SearchStatusRead(
                configured=outcome.configured,
                licensed_configured=outcome.licensed_configured,
                providers_used=outcome.providers_used,
                provider_results=[
                    ProviderResultRead(
                        title=hit.title,
                        url=hit.url,
                        snippet=hit.snippet,
                        company=hit.company or "",
                        published_date=hit.published_date,
                        providers=hit.providers,
                        rank=hit.rank,
                        url_type=hit.url_type or "unverified",
                        source_kind=hit.source_kind or "unknown",
                        trusted_tenant=hit.trusted_tenant,
                    )
                    for hit in outcome.hits
                ],
                provider_statuses=[
                    ProviderStatusRead(
                        name=info.name,
                        label=info.label,
                        role=info.role,
                        configured=info.configured,
                        available=info.available,
                        enabled=info.enabled,
                        reason=info.reason,
                        cost_note=info.cost_note,
                    )
                    for info in (
                        self._search.provider_infos()
                        if hasattr(self._search, "provider_infos")
                        else []
                    )
                ],
                warnings=warnings,
                discovery_window_days=days,
                searched_at=datetime.now(UTC),
                tavily_queries=outcome.provider_queries,
                tavily_cached_queries=outcome.cached_queries,
                credits_estimated=outcome.credits_estimated,
                diagnostics=[
                    CompanySearchDiagnosticRead(
                        company=diagnostic.company,
                        queries=diagnostic.queries,
                        raw_results=diagnostic.raw_results,
                        detail_candidates=diagnostic.detail_candidates,
                        accepted=diagnostic.accepted,
                        dropped_list_or_landing=diagnostic.dropped_list_or_landing,
                        dropped_unrelated=diagnostic.dropped_unrelated,
                        dropped_invalid=diagnostic.dropped_invalid,
                        dropped_filter=diagnostic.dropped_filter,
                        provider_errors=diagnostic.provider_errors,
                        layers=diagnostic.layers,
                        reason=diagnostic.reason,
                    )
                    for diagnostic in outcome.diagnostics
                ],
            ),
            total_jobs=total_jobs,
            total_leads=total_leads,
        )

    def _local_jobs(
        self,
        query: str | None,
        company_keys: list[str],
        city: str | None,
        job_type: str | None,
        job_family: str | None,
        days: int | None,
        sort: str,
        published_within_days: int | None = None,
        verification: str = "all",
    ) -> tuple[list, int]:
        job_sort = "published_at_desc" if sort == "published" else "first_seen_at_desc"
        display_companies = tuple(COMPANY_NAMES[key] for key in company_keys)
        published_after = (
            datetime.now(UTC) - timedelta(days=published_within_days)
            if published_within_days
            else None
        )
        # Agent tools join several keywords into one string ("大模型 LLM Agent").
        # Matching that verbatim matches nothing, so every term is OR-ed.
        terms = tuple(word for word in (query or "").split() if word)
        job_query = JobQuery(
            q=None,
            q_terms=terms,
            companies=display_companies,
            cities=(city,) if city else (),
            job_types=(job_type,) if job_type else (),
            first_seen_after=(datetime.now(UTC) - timedelta(days=days) if days else None),
            published_after=published_after,
            published_date_known=True if published_after else None,
            sort=job_sort,
            page=1,
            page_size=200,
        )
        jobs, total = JobService(self._session, self._settings).list_jobs(job_query)
        if verification == "pending":
            jobs = []
            total = 0
        if job_family:
            jobs = [
                job
                for job in jobs
                if job_family_matches(classify_job_family(job.title, job.description), job_family)
            ]
        return jobs, total

    def close(self) -> None:
        self._search.close()

    def list_leads(
        self,
        user_id: UUID,
        *,
        query: str | None = None,
        company: str | None = None,
    ) -> list[JobLeadRead]:
        return [
            lead_to_read(lead)
            for lead in self._leads.list_for_user(user_id, query=query, company=company, limit=100)
        ]

    def lead_detail(self, lead_id: UUID, user_id: UUID) -> JobLeadRead:
        return lead_to_read(self._leads.get_for_user(lead_id, user_id))
