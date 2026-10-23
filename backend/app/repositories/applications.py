"""Application and status-event access layer (always scoped by user)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.application import Application, ApplicationEvent
from app.db.models.enums import ApplicationStatus


class ApplicationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _with_relations(self, stmt):
        return stmt.options(
            selectinload(Application.events),
            selectinload(Application.job),
            selectinload(Application.lead),
        )

    def get(self, user_id: UUID, application_id: UUID) -> Application | None:
        return self._session.scalar(
            self._with_relations(select(Application)).where(
                Application.id == application_id, Application.user_id == user_id
            )
        )

    def get_for_update(self, user_id: UUID, application_id: UUID) -> Application | None:
        return self._session.scalar(
            self._with_relations(select(Application))
            .where(Application.id == application_id, Application.user_id == user_id)
            .with_for_update()
        )

    def get_by_job(self, user_id: UUID, job_id: UUID) -> Application | None:
        return self._session.scalar(
            self._with_relations(select(Application)).where(
                Application.user_id == user_id, Application.job_id == job_id
            )
        )

    def get_by_lead(self, user_id: UUID, lead_id: UUID) -> Application | None:
        return self._session.scalar(
            self._with_relations(select(Application)).where(
                Application.user_id == user_id, Application.job_lead_id == lead_id
            )
        )

    def get_by_dedupe_key(self, user_id: UUID, dedupe_key: str) -> Application | None:
        return self._session.scalar(
            self._with_relations(select(Application)).where(
                Application.user_id == user_id, Application.dedupe_key == dedupe_key
            )
        )

    def list(
        self,
        user_id: UUID,
        *,
        status: ApplicationStatus | None,
        company: str | None,
        query: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Application], int]:
        conditions = [Application.user_id == user_id]
        if status is not None:
            conditions.append(Application.status == status)
        if company:
            pattern = f"%{company.strip()}%"
            conditions.append(Application.external_company.ilike(pattern))
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    Application.external_title.ilike(pattern),
                    Application.external_company.ilike(pattern),
                )
            )

        total = self._session.scalar(select(func.count(Application.id)).where(*conditions))
        stmt = (
            self._with_relations(select(Application))
            .where(*conditions)
            .order_by(Application.updated_at.desc(), Application.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.scalars(stmt).all()), int(total or 0)

    def events(self, application_id: UUID) -> list[ApplicationEvent]:
        stmt = (
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.event_time.asc(), ApplicationEvent.created_at.asc())
        )
        return list(self._session.scalars(stmt).all())

    def find_event_by_reference(
        self, application_id: UUID, source_type: str, source_reference: str
    ) -> ApplicationEvent | None:
        return self._session.scalar(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == application_id,
                ApplicationEvent.source_type == source_type,
                ApplicationEvent.source_reference == source_reference,
            )
        )

    def add(self, row: Application) -> None:
        self._session.add(row)

    def add_event(self, event: ApplicationEvent) -> None:
        self._session.add(event)

    def delete(self, row: Application) -> None:
        self._session.delete(row)
