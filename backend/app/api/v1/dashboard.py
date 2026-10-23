"""Dashboard aggregate endpoint (real user data only)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.db.models.application import Application, ApplicationEvent
from app.db.models.application_import import ApplicationImport
from app.db.models.enums import ApplicationStatus, SavedListType
from app.db.models.job import Job
from app.db.models.saved_job import SavedJob
from app.schemas.common import DataResponse
from app.schemas.dashboard import (
    DashboardCounts,
    DashboardEvent,
    DashboardJob,
    DashboardSummary,
    DashboardUpcoming,
)
from app.security.csrf import require_csrf

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_csrf)])

_STATUS_COUNT_MAP = {
    "applied": {ApplicationStatus.APPLIED},
    "screening": {ApplicationStatus.SCREENING},
    "assessment": {ApplicationStatus.ASSESSMENT, ApplicationStatus.ONLINE_ASSESSMENT},
    "interview": {ApplicationStatus.INTERVIEW},
    "offer": {ApplicationStatus.OFFER},
    "planned": {ApplicationStatus.PLANNED, ApplicationStatus.TO_APPLY},
}


def _application_rows(session, user):
    return select(Application).where(Application.user_id == user.id)


@router.get(
    "/summary",
    response_model=DataResponse[DashboardSummary],
    summary="求职工作台真实统计与近期数据",
)
def dashboard_summary(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    latest_limit: int = Query(default=6, ge=1, le=20),
    event_limit: int = Query(default=6, ge=1, le=20),
) -> DataResponse[DashboardSummary]:
    saved = int(
        session.scalar(
            select(func.count(SavedJob.id)).where(
                SavedJob.user_id == user.id,
                SavedJob.list_type == SavedListType.SAVED,
            )
        )
        or 0
    )

    counts = DashboardCounts(saved=saved)
    status_counts = dict(
        session.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.user_id == user.id)
            .group_by(Application.status)
        ).all()
    )
    for key, statuses in _STATUS_COUNT_MAP.items():
        setattr(counts, key, sum(int(status_counts.get(status, 0)) for status in statuses))

    counts.needs_review = int(
        session.scalar(
            select(func.count(ApplicationImport.id)).where(
                ApplicationImport.user_id == user.id,
                ApplicationImport.status == "needs_review",
            )
        )
        or 0
    )

    latest_jobs = session.scalars(
        select(Job)
        .where(Job.is_demo.is_(False))
        .order_by(Job.first_seen_at.desc())
        .limit(latest_limit)
    ).all()

    event_rows = session.execute(
        select(ApplicationEvent, Application)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(Application.user_id == user.id)
        .order_by(
            ApplicationEvent.event_time.desc().nullslast(), ApplicationEvent.created_at.desc()
        )
        .limit(event_limit)
    ).all()

    now = datetime.now(UTC)
    upcoming = session.execute(
        select(ApplicationEvent, Application)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(
            Application.user_id == user.id,
            ApplicationEvent.event_time.is_not(None),
            ApplicationEvent.event_time >= now,
            ApplicationEvent.to_status.in_(
                [
                    ApplicationStatus.ASSESSMENT,
                    ApplicationStatus.ONLINE_ASSESSMENT,
                    ApplicationStatus.INTERVIEW,
                ]
            ),
        )
        .order_by(ApplicationEvent.event_time.asc())
        .limit(10)
    ).all()

    return DataResponse(
        data=DashboardSummary(
            counts=counts,
            latest_jobs=[
                DashboardJob(
                    id=job.id,
                    company=job.company.name,
                    title=job.title,
                    city=job.city,
                    job_type=job.job_type,
                    source_url=job.source_url,
                    verification_status=job.verification_status.value,
                    published_at=job.published_at,
                    first_seen_at=job.first_seen_at,
                )
                for job in latest_jobs
            ],
            recent_events=[
                DashboardEvent(
                    id=event.id,
                    application_id=app.id,
                    company=(
                        app.job.company.name if app.job else app.external_company or "未知企业"
                    ),
                    title=(app.job.title if app.job else app.external_title or "未知岗位"),
                    status=event.to_status.value,
                    event_time=event.event_time,
                    source_type=event.source_type,
                    evidence_type=event.evidence_type,
                    verification_status=event.verification_status,
                    summary=(event.evidence_summary or "")[:300] or None,
                )
                for event, app in event_rows
            ],
            upcoming_events=[
                DashboardUpcoming(
                    application_id=app.id,
                    company=(
                        app.job.company.name if app.job else app.external_company or "未知企业"
                    ),
                    title=(app.job.title if app.job else app.external_title or "未知岗位"),
                    status=event.to_status.value,
                    starts_at=event.event_time,
                    source_type=event.source_type,
                    verification_status=event.verification_status,
                )
                for event, app in upcoming
            ],
            generated_at=now,
            date=now.date(),
        )
    )
