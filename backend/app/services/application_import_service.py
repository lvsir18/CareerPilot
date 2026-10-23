"""Email import preview/confirm flow with user isolation and no auto-updates."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.application import Application
from app.db.models.application_import import ApplicationImport
from app.db.models.enums import (
    ApplicationImportStatus,
    ApplicationSourceType,
    ApplicationStatus,
    EventVerificationStatus,
)
from app.db.models.user import User
from app.repositories.applications import ApplicationRepository
from app.schemas.progress_imports import ApplicationImportRead
from app.services.application_service import ApplicationService
from app.services.email_parser import ParsedEmail, parse_eml

MAX_EMAIL_BYTES = 2 * 1024 * 1024


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "")).casefold()


def _application_text(application: Application) -> tuple[str, str]:
    company = application.external_company or (
        application.job.company.name if application.job else ""
    )
    title = application.external_title or (application.job.title if application.job else "")
    return company, title


def import_to_read(row: ApplicationImport, *, duplicate: bool = False) -> ApplicationImportRead:
    return ApplicationImportRead(
        id=row.id,
        status=row.status,
        filename=row.filename,
        subject=row.subject,
        sender=row.sender,
        received_at=row.received_at,
        parsed_company=row.parsed_company,
        parsed_title=row.parsed_title,
        parsed_status=row.parsed_status,
        parsed_event_time=row.parsed_event_time,
        confidence=row.confidence,
        matched_application_id=row.matched_application_id,
        confirmed_event_id=row.confirmed_event_id,
        body_excerpt=row.body_excerpt,
        warnings=list(row.warnings_json or []),
        duplicate=duplicate,
        confirmed_at=row.confirmed_at,
        created_at=row.created_at,
    )


class ApplicationImportService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._applications = ApplicationRepository(session)
        self._application_service = ApplicationService(session, settings)

    def _match_application(self, user_id: UUID, parsed: ParsedEmail) -> tuple[UUID | None, float]:
        rows, _ = self._applications.list(
            user_id,
            status=None,
            company=None,
            query=None,
            page=1,
            page_size=200,
        )
        haystack = _normalize(
            " ".join(filter(None, [parsed.subject, parsed.sender, parsed.body_excerpt]))
        )
        scored: list[tuple[int, UUID]] = []
        for application in rows:
            company, title = _application_text(application)
            company_key = _normalize(company)
            title_key = _normalize(title)
            score = 0
            if company_key and company_key in haystack:
                score += 2
            if title_key and title_key in haystack:
                score += 4
            if parsed.company and company_key and _normalize(parsed.company) == company_key:
                score += 2
            if parsed.title and title_key and _normalize(parsed.title) == title_key:
                score += 4
            if score:
                scored.append((score, application.id))
        if not scored:
            return None, 0.0
        scored.sort(key=lambda item: item[0], reverse=True)
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            return None, 0.0
        if scored[0][0] < 2:
            return None, 0.0
        return scored[0][1], min(0.95, 0.5 + scored[0][0] * 0.07)

    def import_email(
        self,
        user: User,
        *,
        filename: str,
        raw: bytes,
    ) -> tuple[ApplicationImport, bool]:
        filename = Path(filename).name
        if not filename.lower().endswith(".eml"):
            raise AppError(
                code="INVALID_EMAIL_FILE",
                message="只接受 .eml 招聘通知邮件",
                status_code=422,
            )
        if not raw:
            raise AppError(code="EMPTY_EMAIL_FILE", message="邮件文件为空", status_code=422)
        if len(raw) > MAX_EMAIL_BYTES:
            raise AppError(
                code="EMAIL_TOO_LARGE",
                message="邮件文件不能超过 2 MB",
                status_code=413,
            )
        content_hash = hashlib.sha256(raw).hexdigest()
        existing = self._session.scalar(
            select(ApplicationImport).where(
                ApplicationImport.user_id == user.id,
                ApplicationImport.content_hash == content_hash,
            )
        )
        if existing is not None:
            return existing, True
        try:
            parsed = parse_eml(raw)
        except ValueError as exc:
            raise AppError(
                code="EMAIL_PARSE_FAILED",
                message=str(exc),
                status_code=422,
            ) from exc
        matched_id, match_confidence = self._match_application(user.id, parsed)
        matched_title = None
        if matched_id is not None:
            matched_application = self._applications.get(user.id, matched_id)
            if matched_application is not None:
                matched_title = _application_text(matched_application)[1] or None
        status = (
            ApplicationImportStatus.READY
            if matched_id is not None and parsed.status is not None
            else ApplicationImportStatus.NEEDS_REVIEW
        )
        warnings = list(parsed.warnings)
        if matched_id is None:
            warnings.append("未唯一匹配到已有申请，确认前请手动选择")
        elif parsed.title is None and matched_title:
            warnings.append("岗位名称由已有申请记录匹配，非邮件明确提取")
        row = ApplicationImport(
            user_id=user.id,
            filename=filename[:255],
            content_hash=content_hash,
            status=status.value,
            subject=parsed.subject,
            sender=parsed.sender,
            received_at=parsed.received_at,
            parsed_company=parsed.company,
            parsed_title=parsed.title or matched_title,
            parsed_status=parsed.status,
            parsed_event_time=parsed.event_time,
            confidence=max(parsed.confidence, match_confidence),
            matched_application_id=matched_id,
            body_excerpt=parsed.body_excerpt,
            warnings_json=warnings,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row, False

    def list_for_user(self, user_id: UUID, *, limit: int = 20) -> list[ApplicationImport]:
        return list(
            self._session.scalars(
                select(ApplicationImport)
                .where(ApplicationImport.user_id == user_id)
                .order_by(ApplicationImport.created_at.desc())
                .limit(limit)
            )
        )

    def get(self, user_id: UUID, import_id: UUID) -> ApplicationImport:
        row = self._session.scalar(
            select(ApplicationImport).where(
                ApplicationImport.id == import_id,
                ApplicationImport.user_id == user_id,
            )
        )
        if row is None:
            raise AppError(
                code="APPLICATION_IMPORT_NOT_FOUND",
                message="邮件导入记录不存在",
                status_code=404,
            )
        return row

    def confirm(
        self,
        user: User,
        import_id: UUID,
        *,
        application_id: UUID | None,
        status: ApplicationStatus | None,
        event_time: datetime | None,
        note: str | None,
    ) -> ApplicationImport:
        row = self.get(user.id, import_id)
        if row.status == ApplicationImportStatus.CONFIRMED.value:
            return row
        target_id = application_id or row.matched_application_id
        if target_id is None:
            raise AppError(
                code="APPLICATION_TARGET_REQUIRED",
                message="请选择要更新的申请记录",
                status_code=422,
            )
        application = self._application_service.get(user, target_id)
        target_status = status or row.parsed_status
        if target_status is None:
            raise AppError(
                code="APPLICATION_STATUS_REQUIRED",
                message="邮件没有明确状态，确认时必须由用户选择",
                status_code=422,
            )
        occurred_at = event_time or row.parsed_event_time or row.received_at or datetime.now(UTC)
        # Only an explicitly parsed status is corroborated by the email. If the
        # user chooses a status the email did not state, it remains user-reported.
        verification = (
            EventVerificationStatus.EMAIL_CONFIRMED
            if row.parsed_status == target_status
            else EventVerificationStatus.USER_REPORTED
        )
        event = self._application_service.add_event(
            user,
            application.id,
            status=target_status,
            event_time=occurred_at,
            note=note,
            evidence_summary=(
                f"邮件导入：{row.subject or row.filename}"
                + (f" / {row.sender}" if row.sender else "")
            )[:2_000],
            source_type=ApplicationSourceType.EMAIL_IMPORT,
            source_reference=f"email:{row.id}",
            verification_status=verification,
        )
        row.status = ApplicationImportStatus.CONFIRMED.value
        row.matched_application_id = application.id
        row.confirmed_event_id = event.id
        row.confirmed_at = datetime.now(UTC)
        self._session.commit()
        self._session.refresh(row)
        return row
