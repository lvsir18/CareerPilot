"""Candidate leads, discovery and evidence contracts."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.db.models.enums import JobSourceMethod, LeadVerificationStatus
from app.db.models.job_lead import JobLead
from app.schemas.evidence import SourceEvidenceRead
from app.schemas.jobs import JobListItem
from app.search.domains import inspect_url
from app.search.taxonomy import classify_job_family


class JobLeadRead(BaseModel):
    id: UUID
    company: str
    title: str
    official_url: str
    summary: str | None
    source_method: JobSourceMethod
    verification_status: LeadVerificationStatus
    published_date: date | None
    first_seen_at: datetime
    last_seen_at: datetime
    last_verified_at: datetime | None
    last_verification_error: str | None
    last_verification_attempt_at: datetime | None
    job_id: UUID | None
    is_private: bool
    job_family: str
    source_kind: str
    url_type: str


class TrustedTenantRead(BaseModel):
    provider: str
    host: str
    path_prefix: str
    entry_url: str
    evidence_url: str
    verified_at: date


class OfficialSourceRead(BaseModel):
    company: str
    name: str
    domains: list[str]
    priority: str
    http_status: int
    final_url: str
    verified_at: date
    detail_verification: str
    note: str
    official_entrypoints: list[str]
    trusted_tenants: list[TrustedTenantRead]
    search_domains: list[str]
    job_url_patterns: list[str]
    verification_status: str
    access_policy: str


class LeadImportRequest(BaseModel):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    city: str | None = Field(default=None, max_length=100)
    job_type: str | None = Field(default=None, max_length=50)
    published_date: date | None = None
    company: str | None = Field(default=None, max_length=50)


class ProviderResultRead(BaseModel):
    title: str
    url: str
    snippet: str | None
    company: str
    published_date: date | None
    providers: list[str]
    rank: int
    url_type: str
    source_kind: str
    trusted_tenant: str | None


class ProviderStatusRead(BaseModel):
    name: str
    label: str
    role: str
    configured: bool
    available: bool
    enabled: bool
    reason: str | None
    cost_note: str | None


class CompanySearchDiagnosticRead(BaseModel):
    company: str
    queries: int
    raw_results: int
    detail_candidates: int
    accepted: int
    dropped_list_or_landing: int
    dropped_unrelated: int
    dropped_invalid: int
    dropped_filter: int
    provider_errors: int
    layers: list[str]
    reason: str | None


class SearchStatusRead(BaseModel):
    configured: bool
    licensed_configured: bool
    providers_used: list[str]
    provider_results: list[ProviderResultRead]
    provider_statuses: list[ProviderStatusRead]
    warnings: list[str]
    discovery_window_days: int | None
    searched_at: datetime
    tavily_queries: int
    tavily_cached_queries: int
    credits_estimated: int
    diagnostics: list[CompanySearchDiagnosticRead]


class DiscoveryResponse(BaseModel):
    query: str | None
    companies: list[str]
    job_family: str | None
    sort: str
    verification: str
    published_within_days: int | None
    page: int
    page_size: int
    total_pages: int
    jobs: list[JobListItem]
    leads: list[JobLeadRead]
    search: SearchStatusRead
    total_jobs: int
    total_leads: int


class JobLeadDetail(BaseModel):
    lead: JobLeadRead
    evidence: list[SourceEvidenceRead]


class LeadVerificationResult(BaseModel):
    lead: JobLeadRead
    job_id: UUID
    created: bool
    updated: bool


def lead_to_read(lead: JobLead) -> JobLeadRead:
    inspected = inspect_url(lead.official_url)
    source_kind = (
        "user_private"
        if lead.owner_user_id is not None
        else (inspected.source_kind if inspected else "unknown")
    )
    return JobLeadRead(
        id=lead.id,
        company=lead.company.name,
        title=lead.title,
        official_url=lead.official_url,
        summary=lead.summary,
        source_method=lead.source_method,
        verification_status=lead.verification_status,
        published_date=lead.published_date,
        first_seen_at=lead.first_seen_at,
        last_seen_at=lead.last_seen_at,
        last_verified_at=lead.last_verified_at,
        last_verification_error=lead.last_verification_error,
        last_verification_attempt_at=lead.last_verification_attempt_at,
        job_id=lead.job_id,
        is_private=lead.owner_user_id is not None,
        job_family=classify_job_family(lead.title, lead.summary),
        source_kind=source_kind,
        url_type=inspected.url_type if inspected else "unverified",
    )
