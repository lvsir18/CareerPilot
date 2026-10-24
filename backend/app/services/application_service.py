"""Application tracking with explicit source evidence and preserved history."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.application import Application, ApplicationEvent
from app.db.models.enums import (
    ApplicationSourceType,
    ApplicationStatus,
    EventVerificationStatus,
)
from app.db.models.user import User
from app.repositories.applications import ApplicationRepository
from app.services.job_lead_service import JobLeadService
from app.services.job_service import JobService

# Statuses that can carry a scheduled time (exam / interview slot).
_SCHEDULED_STATUSES = {
    ApplicationStatus.ASSESSMENT,
    ApplicationStatus.ONLINE_ASSESSMENT,
    ApplicationStatus.INTERVIEW,
}


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AppError(
            code="INVALID_OFFICIAL_URL",
            message="岗位链接必须是 http/https 官方链接",
            status_code=422,
        )
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.query,
            "",
        )
    )


def _url_key(value: str) -> str:
    return hashlib.sha256(_canonical_url(value).encode("utf-8")).hexdigest()[:48]


class ApplicationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repository = ApplicationRepository(session)
        self._jobs = JobService(session, settings)
        self._leads = JobLeadService(session, settings)

    def _target(
        self,
        user_id: UUID,
        *,
        job_id: UUID | None,
        job_lead_id: UUID | None,
        external_company: str | None,
        external_title: str | None,
        external_url: str | None,
    ) -> tuple[UUID | None, UUID | None, str, str, str | None, str]:
        resolved_job_id = job_id
        resolved_lead_id = job_lead_id
        company = (external_company or "").strip()
        title = (external_title or "").strip()
        url = _canonical_url(external_url) if external_url else None
        dedupe_key: str

        if job_id:
            job = self._jobs.get_job(job_id)
            company = job.company.name
            title = job.title
            url = job.source_url
            dedupe_key = f"job:{job.id}"
        elif job_lead_id:
            lead = self._leads.get_for_user(job_lead_id, user_id)
            resolved_job_id = lead.job_id
            if lead.job_id:
                job = self._jobs.get_job(lead.job_id)
                company = job.company.name
                title = job.title
                url = job.source_url
                dedupe_key = f"job:{job.id}"
            else:
                company = lead.company.name
                title = lead.title
                url = lead.official_url
                dedupe_key = f"lead:{lead.id}"
        else:
            if not company or not title or not url:
                raise AppError(
                    code="APPLICATION_TARGET_REQUIRED",
                    message="必须选择岗位/候选岗位，或提供公司、岗位名称和官方链接",
                    status_code=422,
                )
            dedupe_key = f"url:{_url_key(url)}"

        return resolved_job_id, resolved_lead_id, company, title, url, dedupe_key

    def _snapshot(
        self,
        *,
        job_id: UUID | None,
        lead_id: UUID | None,
        company: str,
        title: str,
        url: str | None,
        notes: str | None,
        status: ApplicationStatus,
        applied_at: datetime | None,
        dedupe_key: str,
    ) -> Application:
        now = datetime.now(UTC)
        application = Application(
            user_id=None,  # set by caller
            job_id=job_id,
            job_lead_id=lead_id,
            external_company=company[:200],
            external_title=title[:300],
            external_url=url,
            status=status,
            notes=notes,
            applied_at=applied_at or (now if status == ApplicationStatus.APPLIED else None),
            last_confirmed_at=now,
            source_of_truth="user_manual",
            source_type=ApplicationSourceType.MANUAL.value,
            dedupe_key=dedupe_key,
        )
        return application

    def create(
        self,
        user: User,
        *,
        job_id: UUID | None,
        job_lead_id: UUID | None,
        external_company: str | None,
        external_title: str | None,
        external_url: str | None,
        status: ApplicationStatus,
        notes: str | None,
        applied_at: datetime | None,
    ) -> Application:
        (
            resolved_job_id,
            resolved_lead_id,
            company,
            title,
            url,
            dedupe_key,
        ) = self._target(
            user.id,
            job_id=job_id,
            job_lead_id=job_lead_id,
            external_company=external_company,
            external_title=external_title,
            external_url=external_url,
        )
        existing = self._repository.get_by_dedupe_key(user.id, dedupe_key)
        if existing is None and resolved_job_id:
            existing = self._repository.get_by_job(user.id, resolved_job_id)
        if existing is not None:
            raise AppError(
                code="APPLICATION_EXISTS",
                message="该岗位已有申请记录",
                status_code=409,
                details={"application_id": str(existing.id)},
            )

        application = self._snapshot(
            job_id=resolved_job_id,
            lead_id=resolved_lead_id,
            company=company,
            title=title,
            url=url,
            notes=notes,
            status=status,
            applied_at=applied_at,
            dedupe_key=dedupe_key,
        )
        application.user_id = user.id
        self._repository.add(application)
        self._session.flush()
        initial_event = self._add_event(
            application,
            status=status,
            event_time=applied_at or datetime.now(UTC),
            note=notes,
            source_type=ApplicationSourceType.MANUAL,
            source_reference=None,
            evidence_summary="用户手动登记申请",
            verification_status=EventVerificationStatus.USER_REPORTED,
        )
        # Initial creation has no previous state, even though ``_add_event``
        # assigns the just-created status before the event is persisted.
        initial_event.from_status = None
        self._session.commit()
        self._session.refresh(application)
        return application

    def _add_event(
        self,
        application: Application,
        *,
        status: ApplicationStatus,
        event_time: datetime,
        note: str | None,
        source_type: ApplicationSourceType,
        source_reference: str | None,
        evidence_summary: str | None,
        verification_status: EventVerificationStatus,
        is_scheduled: bool = False,
    ) -> ApplicationEvent:
        previous = application.status
        event = ApplicationEvent(
            application_id=application.id,
            from_status=previous,
            to_status=status,
            event_time=event_time,
            actor="user" if source_type == ApplicationSourceType.MANUAL else "system",
            evidence_type=source_type.value,
            source_type=source_type.value,
            source_reference=source_reference,
            evidence_summary=evidence_summary,
            verification_status=verification_status.value,
            note=note,
            is_scheduled=is_scheduled,
        )
        application.status = status
        # A future appointment is created *now*: "最近确认" is the moment the user
        # recorded it, while the calendar keeps the interview slot itself.
        application.last_confirmed_at = datetime.now(UTC) if is_scheduled else event_time
        application.source_type = source_type.value
        application.source_reference = source_reference
        if status == ApplicationStatus.APPLIED and application.applied_at is None:
            application.applied_at = event_time
        self._repository.add_event(event)
        return event

    def add_event(
        self,
        user: User,
        application_id: UUID,
        *,
        status: ApplicationStatus,
        event_time: datetime | None,
        note: str | None,
        evidence_summary: str | None,
        source_type: ApplicationSourceType,
        source_reference: str | None,
        verification_status: EventVerificationStatus,
        supersede_scheduled: bool = False,
        reschedule_event_id: UUID | None = None,
    ) -> ApplicationEvent:
        application = self._repository.get_for_update(user.id, application_id)
        if application is None:
            raise AppError(
                code="APPLICATION_NOT_FOUND",
                message="申请记录不存在",
                status_code=404,
            )
        if source_reference:
            existing = self._repository.find_event_by_reference(
                application.id, source_type.value, source_reference
            )
            if existing is not None:
                return existing
        scheduled = event_time is not None and status in _SCHEDULED_STATUSES
        if supersede_scheduled or reschedule_event_id is not None:
            if not scheduled:
                raise AppError(
                    code="INVALID_RESCHEDULE",
                    message="改期需要明确的预约类型和时间",
                    status_code=422,
                )
            if reschedule_event_id is not None:
                target = self._repository.get_event(application.id, reschedule_event_id)
                if target is None or not target.is_scheduled:
                    raise AppError(
                        code="APPLICATION_EVENT_NOT_FOUND", message="预约不存在", status_code=404
                    )
                if target.superseded_at is not None:
                    raise AppError(
                        code="APPOINTMENT_NOT_ACTIVE",
                        message="该预约已改期或取消，请刷新后重试",
                        status_code=409,
                    )
                if target.to_status != status:
                    raise AppError(
                        code="APPOINTMENT_TYPE_MISMATCH",
                        message="改期需保持原预约类型",
                        status_code=409,
                    )
            else:
                candidates = [
                    event
                    for event in self._repository.events(application.id)
                    if event.is_scheduled
                    and event.superseded_at is None
                    and event.to_status == status
                ]
                if len(candidates) != 1:
                    raise AppError(
                        code="APPOINTMENT_SELECTION_REQUIRED",
                        message="请选择具体要改期的预约，其他轮次将保留",
                        status_code=409,
                    )
                target = candidates[0]
            # The application lock serializes edits; retire only this event in
            # the same transaction as creating its replacement.
            target.superseded_at = datetime.now(UTC)
        event = self._add_event(
            application,
            status=status,
            event_time=event_time or datetime.now(UTC),
            note=note,
            source_type=source_type,
            source_reference=source_reference,
            evidence_summary=evidence_summary,
            verification_status=verification_status,
            # Only an explicit time on an assessment/interview event is a
            # calendar appointment; a bare status change is not.
            is_scheduled=scheduled,
        )
        self._session.commit()
        self._session.refresh(event)
        self._session.refresh(application)
        return event

    def cancel_event(self, user: User, application_id: UUID, event_id: UUID) -> ApplicationEvent:
        """Cancel one appointment without deleting the audit trail."""
        application = self._repository.get_for_update(user.id, application_id)
        if application is None:
            raise AppError(code="APPLICATION_NOT_FOUND", message="申请记录不存在", status_code=404)
        event = self._repository.get_event(application.id, event_id)
        if event is None or not event.is_scheduled:
            raise AppError(
                code="APPLICATION_EVENT_NOT_FOUND",
                message="这条预约不存在或不是可取消的日程",
                status_code=404,
            )
        if event.superseded_at is None:
            event.superseded_at = datetime.now(UTC)
            self._session.commit()
            self._session.refresh(event)
        return event

    def update_status(
        self,
        user: User,
        application_id: UUID,
        *,
        status: ApplicationStatus,
        note: str | None,
        applied_at: datetime | None,
    ) -> Application:
        application = self._repository.get_for_update(user.id, application_id)
        if application is None:
            raise AppError(
                code="APPLICATION_NOT_FOUND",
                message="申请记录不存在",
                status_code=404,
            )
        if application.status == status:
            raise AppError(
                code="APPLICATION_STATUS_UNCHANGED",
                message="状态未发生变化",
                status_code=409,
            )
        event_time = applied_at or datetime.now(UTC)
        self._add_event(
            application,
            status=status,
            event_time=event_time,
            note=note,
            source_type=ApplicationSourceType.MANUAL,
            source_reference=None,
            evidence_summary="用户手动更新状态",
            verification_status=EventVerificationStatus.USER_REPORTED,
        )
        if applied_at is not None:
            application.applied_at = applied_at
        self._session.commit()
        self._session.refresh(application)
        return application

    def update_metadata(
        self,
        user: User,
        application_id: UUID,
        *,
        notes: str | None,
        external_company: str | None,
        external_title: str | None,
        external_url: str | None,
    ) -> Application:
        application = self._repository.get_for_update(user.id, application_id)
        if application is None:
            raise AppError(
                code="APPLICATION_NOT_FOUND",
                message="申请记录不存在",
                status_code=404,
            )
        if notes is not None:
            application.notes = notes
        if external_company is not None:
            application.external_company = external_company.strip()[:200]
        if external_title is not None:
            application.external_title = external_title.strip()[:300]
        if external_url is not None:
            application.external_url = _canonical_url(external_url)
        self._session.commit()
        self._session.refresh(application)
        return application

    def list(
        self,
        user: User,
        *,
        status: ApplicationStatus | None,
        company: str | None,
        query: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Application], int]:
        return self._repository.list(
            user.id,
            status=status,
            company=company,
            query=query,
            page=page,
            page_size=page_size,
        )

    def get(self, user: User, application_id: UUID) -> Application:
        application = self._repository.get(user.id, application_id)
        if application is None:
            raise AppError(
                code="APPLICATION_NOT_FOUND",
                message="申请记录不存在",
                status_code=404,
            )
        return application

    def events(self, user: User, application_id: UUID) -> list[ApplicationEvent]:
        self.get(user, application_id)
        return self._repository.events(application_id)

    def delete(self, user: User, application_id: UUID) -> None:
        application = self._repository.get_for_update(user.id, application_id)
        if application is None:
            raise AppError(
                code="APPLICATION_NOT_FOUND",
                message="申请记录不存在",
                status_code=404,
            )
        self._repository.delete(application)
        self._session.commit()
