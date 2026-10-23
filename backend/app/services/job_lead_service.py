"""Candidate lead persistence, private imports and official-page verification."""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.connectors.baidu import BaiduPublicConnector
from app.connectors.errors import ConnectorError
from app.connectors.schemas import RawJob
from app.core.cache import get_redis
from app.core.config import Settings
from app.core.errors import AppError
from app.core.text import normalize_company_name
from app.db.models.enums import (
    JobSourceMethod,
    LeadVerificationStatus,
    VerificationStatus,
)
from app.db.models.job import Company, Job, JobSource
from app.db.models.job_lead import JobLead, SourceEvidence
from app.schemas.evidence import SourceEvidenceRead
from app.search.base import SearchHit
from app.search.domains import (
    COMPANY_NAMES,
    canonical_official_url,
    classify_url,
    resolve_company,
)
from app.services.jd_parser import parse_jd, parsed_jd_to_datetime
from app.services.job_ingestion import UpsertOutcome, upsert_raw_job
from app.services.tavily_extract import TavilyExtractService


def _hash(*parts: str | None) -> str:
    return hashlib.sha256("|".join(part or "" for part in parts).encode("utf-8")).hexdigest()


class JobLeadService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        extractor: TavilyExtractService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._extractor = extractor

    def _company(self, company_key: str) -> Company:
        display = COMPANY_NAMES.get(company_key, company_key)
        normalized = normalize_company_name(display)
        company = self._session.scalar(select(Company).where(Company.normalized_name == normalized))
        if company is None:
            company = Company(name=display, normalized_name=normalized)
            self._session.add(company)
            self._session.flush()
        return company

    def _public_source(self) -> JobSource:
        source = self._session.scalar(
            select(JobSource).where(
                JobSource.source_type == "baidu_public",
                JobSource.source_key == "baidu-public",
            )
        )
        if source is None:
            source = JobSource(
                source_type="baidu_public",
                source_key="baidu-public",
                config_json={},
                enabled=False,
            )
            self._session.add(source)
            self._session.flush()
        return source

    def _extract_source(self) -> JobSource:
        source = self._session.scalar(
            select(JobSource).where(
                JobSource.source_type == "tavily_extract",
                JobSource.source_key == "tavily-extract",
            )
        )
        if source is None:
            source = JobSource(
                source_type="tavily_extract",
                source_key="tavily-extract",
                config_json={},
                enabled=False,
            )
            self._session.add(source)
            self._session.flush()
        return source

    def _add_evidence(
        self,
        *,
        lead_id: UUID | None,
        job_id: UUID | None,
        source_url: str,
        evidence_kind: str,
        verification_method: str,
        content_hash: str | None,
        evidence_ref: str | None = None,
    ) -> None:
        conditions = [
            SourceEvidence.lead_id == lead_id,
            SourceEvidence.job_id == job_id,
            SourceEvidence.source_url == source_url,
            SourceEvidence.evidence_kind == evidence_kind,
            SourceEvidence.content_hash == content_hash,
        ]
        if evidence_ref is None:
            conditions.append(SourceEvidence.evidence_ref.is_(None))
        else:
            conditions.append(SourceEvidence.evidence_ref == evidence_ref)
        if self._session.scalar(select(SourceEvidence.id).where(*conditions)) is not None:
            return
        self._session.add(
            SourceEvidence(
                lead_id=lead_id,
                job_id=job_id,
                source_url=source_url,
                evidence_kind=evidence_kind,
                verification_method=verification_method,
                content_hash=content_hash,
                evidence_ref=evidence_ref,
            )
        )

    def upsert_search_hit(self, hit: SearchHit) -> JobLead:
        official = canonical_official_url(hit.url)
        hit_company = resolve_company(hit.company)
        if hit_company and hit_company != official.company:
            raise AppError(
                code="LEAD_COMPANY_MISMATCH",
                message="搜索结果公司与官方域名不一致",
                status_code=422,
            )
        company_key = official.company
        title = (hit.title or "").strip()[:300]
        if not title:
            raise AppError(
                code="LEAD_TITLE_MISSING",
                message="搜索结果缺少岗位名称",
                status_code=422,
            )
        company = self._company(company_key)
        dedupe_key = _hash("public", official.url)
        content_hash = _hash(title, official.url, hit.snippet, hit.city, hit.job_type)
        providers = hit.providers or ([hit.provider] if hit.provider else [None])
        lead = self._session.scalar(select(JobLead).where(JobLead.dedupe_key == dedupe_key))
        if lead is None:
            lead = JobLead(
                owner_user_id=None,
                company_id=company.id,
                title=title,
                official_url=official.url,
                summary=hit.snippet,
                source_method=JobSourceMethod.SEARCH_DISCOVERY,
                verification_status=LeadVerificationStatus.SEARCH_SNIPPET_ONLY,
                published_date=hit.published_date,
                first_seen_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
                source_payload_hash=content_hash,
                dedupe_key=dedupe_key,
            )
            self._session.add(lead)
            self._session.flush()
            for provider in providers:
                self._add_evidence(
                    lead_id=lead.id,
                    job_id=None,
                    source_url=official.url,
                    evidence_kind="search_result",
                    verification_method="search_provider",
                    content_hash=content_hash,
                    evidence_ref=provider,
                )
        else:
            lead.last_seen_at = datetime.now(UTC)
            if lead.verification_status == LeadVerificationStatus.STALE:
                lead.verification_status = LeadVerificationStatus.SEARCH_SNIPPET_ONLY
            if lead.source_payload_hash != content_hash:
                lead.title = title
                lead.summary = hit.snippet
                lead.published_date = hit.published_date or lead.published_date
                lead.source_payload_hash = content_hash
            for provider in providers:
                self._add_evidence(
                    lead_id=lead.id,
                    job_id=lead.job_id,
                    source_url=official.url,
                    evidence_kind="search_result",
                    verification_method="search_provider",
                    content_hash=content_hash,
                    evidence_ref=provider,
                )
        return lead

    def import_private(
        self,
        *,
        user_id: UUID,
        url: str,
        title: str,
        description: str | None,
        city: str | None = None,
        job_type: str | None = None,
        published_date: date | None = None,
        company: str | None = None,
    ) -> JobLead:
        official = canonical_official_url(url)
        provided_company = resolve_company(company)
        if provided_company and provided_company != official.company:
            raise AppError(
                code="LEAD_COMPANY_MISMATCH",
                message="填写的公司与官方域名不一致",
                status_code=422,
            )
        company_key = official.company
        company_row = self._company(company_key)
        dedupe_key = _hash("user", str(user_id), official.url)
        lead = self._session.scalar(select(JobLead).where(JobLead.dedupe_key == dedupe_key))
        content_hash = _hash(title, description, official.url, city, job_type)
        if lead is None:
            lead = JobLead(
                owner_user_id=user_id,
                company_id=company_row.id,
                title=title.strip()[:300],
                official_url=official.url,
                summary=(description or "")[:20_000] or None,
                source_method=JobSourceMethod.MANUAL_IMPORT,
                verification_status=LeadVerificationStatus.USER_PROVIDED,
                published_date=published_date,
                first_seen_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
                source_payload_hash=content_hash,
                dedupe_key=dedupe_key,
            )
            self._session.add(lead)
            self._session.flush()
            self._add_evidence(
                lead_id=lead.id,
                job_id=None,
                source_url=official.url,
                evidence_kind="user_paste",
                verification_method="user_confirmed",
                content_hash=content_hash,
            )
        else:
            lead.title = title.strip()[:300]
            lead.summary = (description or "")[:20_000] or None
            lead.last_seen_at = datetime.now(UTC)
            lead.source_payload_hash = content_hash
        self._session.commit()
        self._session.refresh(lead)
        return lead

    def get_for_user(self, lead_id: UUID, user_id: UUID) -> JobLead:
        lead = self._session.scalar(
            select(JobLead).where(
                JobLead.id == lead_id,
                or_(JobLead.owner_user_id.is_(None), JobLead.owner_user_id == user_id),
            )
        )
        if lead is None:
            raise AppError(
                code="JOB_LEAD_NOT_FOUND",
                message="候选岗位不存在",
                status_code=404,
            )
        return lead

    def list_for_user(
        self,
        user_id: UUID,
        *,
        query: str | None = None,
        company: str | None = None,
        companies: list[str] | None = None,
        job_family: str | None = None,
        days: int | None = None,
        limit: int = 50,
        sort: str = "relevance",
    ) -> list[JobLead]:
        conditions = [or_(JobLead.owner_user_id.is_(None), JobLead.owner_user_id == user_id)]
        company_keys = list(companies or [])
        if company:
            company_keys.append(company)
        resolved = [
            key for key in (resolve_company(value) for value in company_keys) if key is not None
        ]
        if resolved:
            company_ids = [self._company(key).id for key in dict.fromkeys(resolved)]
            conditions.append(JobLead.company_id.in_(company_ids))
        if days:
            from datetime import timedelta

            conditions.append(JobLead.first_seen_at >= datetime.now(UTC) - timedelta(days=days))
        order = (
            (JobLead.published_date.desc().nullslast(), JobLead.last_seen_at.desc())
            if sort == "published"
            else (JobLead.last_seen_at.desc(), JobLead.first_seen_at.desc())
        )
        stmt = select(JobLead).where(*conditions).order_by(*order).limit(limit)
        leads = list(self._session.scalars(stmt))
        if query:
            tokens = [token for token in query.split() if token]
            leads = [
                lead
                for lead in leads
                if not tokens
                or any(token in f"{lead.title} {lead.summary or ''}" for token in tokens)
            ]
        if job_family:
            from app.search.taxonomy import classify_job_family

            leads = [
                lead
                for lead in leads
                if classify_job_family(lead.title, lead.summary) == job_family
            ]
        return leads

    def evidence_for_lead(self, lead_id: UUID) -> list[SourceEvidenceRead]:
        rows = self._session.scalars(
            select(SourceEvidence)
            .where(SourceEvidence.lead_id == lead_id)
            .order_by(SourceEvidence.captured_at.desc())
        )
        return [evidence_to_read(row) for row in rows]

    def evidence_for_job(self, job_id: UUID) -> list[SourceEvidenceRead]:
        rows = self._session.scalars(
            select(SourceEvidence)
            .where(SourceEvidence.job_id == job_id)
            .order_by(SourceEvidence.captured_at.desc())
        )
        return [evidence_to_read(row) for row in rows]

    def verify(self, lead_id: UUID, user_id: UUID) -> tuple[JobLead, UpsertOutcome]:
        lead = self.get_for_user(lead_id, user_id)
        if (
            lead.job_id is not None
            and lead.verification_status == LeadVerificationStatus.VERIFIED_OFFICIAL
        ):
            raise AppError(
                code="JOB_LEAD_ALREADY_VERIFIED",
                message="该候选岗位已完成官方核验",
                status_code=409,
            )
        try:
            redis = get_redis()
            key = f"cp:lead-verify:{user_id}:{int(time.time() // 60)}"
            pipeline = redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, 90)
            count, _ = pipeline.execute()
            if int(count) > self._settings.lead_verify_rate_limit_per_minute:
                raise AppError(
                    code="VERIFICATION_RATE_LIMITED",
                    message="核验操作过于频繁，请稍后再试",
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        except AppError:
            raise
        except Exception:
            # Verification remains usable if Redis is unavailable.
            pass

        try:
            official = classify_url(lead.official_url)
        except ValueError as exc:
            self._mark_verification_failure(lead, f"INVALID_SOURCE_URL: {exc}")
            self._add_evidence(
                lead_id=lead.id,
                job_id=None,
                source_url=lead.official_url,
                evidence_kind="verification_attempt",
                verification_method="none",
                content_hash=None,
                evidence_ref=f"INVALID_SOURCE_URL: {exc}"[:500],
            )
            self._session.commit()
            raise AppError(
                code="INVALID_SOURCE_URL",
                message=f"该链接不是可信职位详情页：{exc}",
                status_code=422,
            ) from exc
        if official.company == "baidu":
            return self._verify_baidu(lead)
        return self._verify_with_extract(lead, official, user_id)

    def _mark_verification_failure(self, lead: JobLead, message: str) -> None:
        lead.last_verification_attempt_at = datetime.now(UTC)
        lead.last_verification_error = message[:500]

    def _verify_baidu(self, lead: JobLead) -> tuple[JobLead, UpsertOutcome]:
        connector = BaiduPublicConnector(self._settings)
        try:
            raw = connector.fetch_job_detail(lead.official_url)
        except ConnectorError as exc:
            self._mark_verification_failure(lead, exc.message)
            self._add_evidence(
                lead_id=lead.id,
                job_id=None,
                source_url=lead.official_url,
                evidence_kind="verification_attempt",
                verification_method="none",
                content_hash=None,
                evidence_ref=exc.message[:500],
            )
            self._session.commit()
            raise AppError(
                code="VERIFICATION_FAILED",
                message=exc.message,
                status_code=422,
            ) from exc
        finally:
            connector.close()
        source = self._public_source()
        return self._persist_verified_job(
            lead,
            source,
            raw,
            verification_method="public_page_parse",
        )

    def _verify_with_extract(
        self, lead: JobLead, official: object, user_id: UUID
    ) -> tuple[JobLead, UpsertOutcome]:
        extractor = self._extractor or TavilyExtractService(self._settings)
        owns_extractor = self._extractor is None
        try:
            page = extractor.extract(lead.official_url, user_id=user_id)
        finally:
            if owns_extractor:
                extractor.close()
        if not page.success or not page.content:
            reason = (page.error or "Tavily Extract 未返回正文")[:500]
            self._mark_verification_failure(lead, reason)
            self._add_evidence(
                lead_id=lead.id,
                job_id=None,
                source_url=lead.official_url,
                evidence_kind="verification_attempt",
                verification_method="none",
                content_hash=None,
                evidence_ref=reason,
            )
            self._session.commit()
            raise AppError(
                code="JD_EXTRACTION_FAILED",
                message=f"岗位详情提取失败：{reason}",
                status_code=422,
                details={"official_url": lead.official_url},
            )

        parsed = parse_jd(
            page.content,
            company_key=official.company,
            official_url=official.url,
            fallback_title=lead.title,
        )
        if not parsed.is_complete:
            reason = "；".join(parsed.incomplete_reasons)[:500]
            self._mark_verification_failure(lead, f"JD_INCOMPLETE: {reason}")
            self._add_evidence(
                lead_id=lead.id,
                job_id=None,
                source_url=lead.official_url,
                evidence_kind="verification_attempt",
                verification_method="none",
                content_hash=None,
                evidence_ref=f"JD_INCOMPLETE: {reason}"[:500],
            )
            self._session.commit()
            raise AppError(
                code="JD_INCOMPLETE",
                message=f"提取成功但 JD 不完整：{reason}",
                status_code=422,
                details={
                    "official_url": lead.official_url,
                    "field_sources": parsed.field_sources,
                },
            )

        now = datetime.now(UTC)
        source_job_id = parsed.official_job_id or _hash(official.url)[:32]
        raw = RawJob(
            source_type="tavily_extract",
            source_key="tavily-extract",
            source_job_id=f"{official.company}:{source_job_id}"[:200],
            company=COMPANY_NAMES.get(official.company, official.company),
            title=(parsed.title or lead.title).strip()[:300],
            source_url=official.url,
            description=parsed.description,
            department=parsed.department,
            location_text=parsed.location,
            city=None,
            job_type=parsed.job_type,
            recruitment_program=None,
            requirements=parsed.requirements,
            published_at=parsed_jd_to_datetime(parsed.published_date),
            raw_payload={
                "extraction": "tavily_extract",
                "extract_depth": self._settings.tavily_extract_depth,
                "field_sources": parsed.field_sources,
                "official_job_id": parsed.official_job_id,
                "skills": parsed.skills,
                "trusted_tenant": official.tenant_host,
                "confidence": parsed.confidence,
            },
            source_method=JobSourceMethod.PUBLIC_PAGE,
            verification_status=VerificationStatus.VERIFIED,
            verified_at=now,
        )
        source = self._extract_source()
        return self._persist_verified_job(
            lead,
            source,
            raw,
            verification_method="tavily_extract",
        )

    def _persist_verified_job(
        self,
        lead: JobLead,
        source: JobSource,
        raw: RawJob,
        *,
        verification_method: str,
    ) -> tuple[JobLead, UpsertOutcome]:
        outcome = upsert_raw_job(self._session, source, raw)
        job = self._session.scalar(
            select(Job).where(
                Job.source_id == source.id,
                Job.source_job_id == raw.source_job_id,
            )
        )
        if job is None:  # pragma: no cover - defensive
            raise AppError(
                code="VERIFICATION_FAILED", message="核验后未能保存岗位", status_code=500
            )
        lead.job_id = job.id
        lead.verification_status = LeadVerificationStatus.VERIFIED_OFFICIAL
        lead.last_verification_error = None
        lead.last_verification_attempt_at = datetime.now(UTC)
        lead.last_verified_at = datetime.now(UTC)
        lead.last_seen_at = lead.last_verified_at
        source.last_job_count = int(
            self._session.scalar(select(func.count(Job.id)).where(Job.source_id == source.id)) or 0
        )
        self._add_evidence(
            lead_id=lead.id,
            job_id=job.id,
            source_url=lead.official_url,
            evidence_kind="official_page",
            verification_method=verification_method,
            content_hash=job.content_hash,
        )
        self._session.commit()
        self._session.refresh(lead)
        return lead, outcome


def evidence_to_read(evidence: SourceEvidence) -> SourceEvidenceRead:
    return SourceEvidenceRead(
        id=evidence.id,
        source_url=evidence.source_url,
        evidence_kind=evidence.evidence_kind,
        captured_at=evidence.captured_at,
        verification_method=evidence.verification_method,
        evidence_ref=evidence.evidence_ref,
        content_hash=evidence.content_hash,
    )
