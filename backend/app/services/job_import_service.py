"""User-initiated official link import with manual-paste fallback.

Only one public page is fetched per user action. There is no crawl queue,
pagination, login, cookie reuse or anti-bot bypass.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.baidu import BaiduPublicConnector
from app.connectors.errors import ConnectorError, ConnectorNotConfigured, ConnectorParseError
from app.connectors.schemas import RawJob
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.enums import (
    JobSourceMethod,
    JobStatus,
    VerificationStatus,
)
from app.db.models.job import Job, JobSource
from app.schemas.imports import ImportPreview, JobImportRequest, preview_from_raw
from app.services.job_ingestion import UpsertOutcome, upsert_raw_job

_BAIDU_UUID = re.compile(r"/jobs/detail/[A-Z]+/([0-9a-fA-F-]{36})/?")


class JobImportService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def _connector(self) -> BaiduPublicConnector:
        return BaiduPublicConnector(self._settings)

    def _source(self) -> JobSource:
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
                enabled=False,  # imports only; never a scheduled bulk source
            )
            self._session.add(source)
            self._session.flush()
        return source

    def preview(self, url: str) -> ImportPreview:
        connector = self._connector()
        try:
            canonical = connector.validate_url(url)
            raw = connector.fetch_job_detail(canonical)
        except ConnectorNotConfigured as exc:
            raise AppError(
                code="INVALID_IMPORT_URL",
                message=exc.message,
                status_code=422,
            ) from exc
        except ConnectorParseError as exc:
            raise AppError(
                code="IMPORT_PAGE_UNREADABLE",
                message=exc.message,
                status_code=422,
                details={"manual_paste_supported": True},
            ) from exc
        except ConnectorError as exc:
            raise AppError(
                code="IMPORT_FETCH_FAILED",
                message="暂时无法读取官方页面，可粘贴已核实的 JD 后确认",
                status_code=502,
                details={"manual_paste_supported": True},
            ) from exc
        finally:
            connector.close()
        return preview_from_raw(raw)

    def _import_raw(self, raw: RawJob) -> tuple[Job, UpsertOutcome]:
        source = self._source()
        outcome = upsert_raw_job(self._session, source, raw)
        source.last_job_count = int(
            self._session.scalar(select(func.count(Job.id)).where(Job.source_id == source.id)) or 0
        )
        self._session.commit()
        job = self._session.scalar(
            select(Job).where(Job.source_id == source.id, Job.source_job_id == raw.source_job_id)
        )
        if job is None:  # pragma: no cover - defensive
            raise AppError(
                code="IMPORT_FAILED",
                message="岗位入库失败",
                status_code=500,
            )
        return job, outcome

    def import_job(self, payload: JobImportRequest, user_id: UUID) -> tuple[Job, UpsertOutcome]:
        url = str(payload.url)
        if not payload.confirmed:
            raise AppError(
                code="IMPORT_CONFIRMATION_REQUIRED",
                message="请先预览并确认岗位信息",
                status_code=422,
            )

        connector = self._connector()
        try:
            canonical = connector.validate_url(url)
        except ConnectorNotConfigured as exc:
            raise AppError(
                code="INVALID_IMPORT_URL",
                message=exc.message,
                status_code=422,
            ) from exc

        if payload.mode != "public_page":
            connector.close()
            raise AppError(
                code="USE_JOB_LEADS_IMPORT",
                message="用户粘贴 JD 默认仅本人可见，请改用 /job-leads/import",
                status_code=422,
            )
        try:
            raw = connector.fetch_job_detail(canonical)
        except ConnectorError as exc:
            raise AppError(
                code="IMPORT_PAGE_UNREADABLE",
                message=exc.message,
                status_code=422,
                details={"manual_paste_supported": True},
            ) from exc
        finally:
            connector.close()
        return self._import_raw(raw)

    def _manual_paste_raw(
        self, payload: JobImportRequest, canonical_url: str, user_id: UUID
    ) -> RawJob:
        if not payload.title or not payload.title.strip():
            raise AppError(
                code="IMPORT_TITLE_REQUIRED",
                message="粘贴模式必须填写岗位名称",
                status_code=422,
            )
        if not payload.company or not payload.company.strip():
            raise AppError(
                code="IMPORT_COMPANY_REQUIRED",
                message="粘贴模式必须填写公司名称",
                status_code=422,
            )
        if not payload.description or not payload.description.strip():
            raise AppError(
                code="IMPORT_DESCRIPTION_REQUIRED",
                message="粘贴模式必须填写职位描述",
                status_code=422,
            )

        match = _BAIDU_UUID.search(urlsplit(canonical_url).path)
        if match:
            source_job_id = match.group(1)
        else:
            material = f"{canonical_url}|{payload.company}|{payload.title}|{user_id}"
            source_job_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]

        published_at = payload.published_at
        if published_at is not None and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)

        return RawJob(
            source_type="baidu_public",
            source_key="baidu-public",
            source_job_id=source_job_id,
            company=payload.company.strip(),
            title=payload.title.strip(),
            source_url=canonical_url,
            description=payload.description.strip(),
            department=None,
            location_text=payload.location_text,
            city=payload.city,
            job_type=payload.job_type,
            recruitment_program=payload.recruitment_program,
            requirements=[item.strip() for item in payload.requirements if item.strip()],
            published_at=published_at,
            raw_payload={
                "import_mode": "manual_paste",
                "user_confirmed": True,
                "user_id": str(user_id),
            },
            is_demo=False,
            status=JobStatus.UNKNOWN,
            source_method=JobSourceMethod.MANUAL_PASTE,
            verification_status=VerificationStatus.USER_CONFIRMED,
            verified_at=datetime.now(UTC),
        )
