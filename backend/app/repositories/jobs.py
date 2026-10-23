"""Job query access layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.text import escape_like, normalize_company_name
from app.db.models.enums import JobStatus
from app.db.models.job import Company, Job, JobSource


@dataclass(frozen=True)
class JobQuery:
    q: str | None = None
    companies: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    job_types: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    recruitment_programs: tuple[str, ...] = ()
    is_demo: bool | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    published_date_known: bool | None = None
    first_seen_after: datetime | None = None
    status: JobStatus | None = None
    sort: str = "published_at_desc"
    page: int = 1
    page_size: int = 20
    include_demo: bool = True
    extra_conditions: tuple = field(default=())


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _conditions(self, query: JobQuery) -> list:
        conditions: list = []
        if not query.include_demo:
            conditions.append(Job.is_demo.is_(False))
        if query.q:
            pattern = f"%{escape_like(query.q.strip())}%"
            conditions.append(
                or_(
                    Job.title.ilike(pattern, escape="\\"),
                    Company.name.ilike(pattern, escape="\\"),
                    Job.description.ilike(pattern, escape="\\"),
                )
            )
        if query.companies:
            normalized = {normalize_company_name(name) for name in query.companies}
            conditions.append(Company.normalized_name.in_(normalized))
        if query.cities:
            city_conditions = []
            for city in query.cities:
                pattern = f"%{escape_like(city)}%"
                city_conditions.append(Job.city.ilike(pattern, escape="\\"))
                city_conditions.append(Job.location_text.ilike(pattern, escape="\\"))
            conditions.append(or_(*city_conditions))
        if query.job_types:
            conditions.append(Job.job_type.in_(query.job_types))
        if query.source_types:
            conditions.append(JobSource.source_type.in_(query.source_types))
        if query.recruitment_programs:
            conditions.append(Job.recruitment_program.in_(query.recruitment_programs))
        if query.is_demo is not None:
            conditions.append(Job.is_demo.is_(query.is_demo))
        if query.published_after is not None:
            conditions.append(Job.published_at >= query.published_after)
        if query.published_before is not None:
            conditions.append(Job.published_at <= query.published_before)
        if query.published_date_known is True:
            conditions.append(Job.published_at.is_not(None))
        elif query.published_date_known is False:
            conditions.append(Job.published_at.is_(None))
        if query.first_seen_after is not None:
            conditions.append(Job.first_seen_at >= query.first_seen_after)
        if query.status is not None:
            conditions.append(Job.status == query.status)
        conditions.extend(query.extra_conditions)
        return conditions

    @staticmethod
    def _ordered(stmt: Select, sort: str) -> Select:
        if sort == "first_seen_at_desc":
            return stmt.order_by(Job.first_seen_at.desc(), Job.id)
        if sort == "title_asc":
            return stmt.order_by(Job.title.asc(), Job.id)
        # Default: real publish dates first; NULL is unknown, never "recent".
        return stmt.order_by(Job.published_at.desc().nullslast(), Job.first_seen_at.desc(), Job.id)

    def list(self, query: JobQuery) -> tuple[list[Job], int]:
        conditions = self._conditions(query)
        count_stmt = (
            select(func.count(Job.id))
            .select_from(Job)
            .join(JobSource, Job.source_id == JobSource.id)
            .join(Company, Job.company_id == Company.id)
            .where(*conditions)
        )
        total = self._session.scalar(count_stmt) or 0

        stmt = (
            select(Job)
            .join(JobSource, Job.source_id == JobSource.id)
            .join(Company, Job.company_id == Company.id)
            .where(*conditions)
        )
        stmt = self._ordered(stmt, query.sort)
        stmt = stmt.offset((query.page - 1) * query.page_size).limit(query.page_size)
        jobs = list(self._session.scalars(stmt).all())
        return jobs, int(total)

    def get(self, job_id: UUID, *, include_demo: bool) -> Job | None:
        stmt = select(Job).where(Job.id == job_id)
        if not include_demo:
            stmt = stmt.where(Job.is_demo.is_(False))
        return self._session.scalar(stmt)

    def by_source_and_job_id(self, source_id: UUID, source_job_id: str) -> Job | None:
        return self._session.scalar(
            select(Job).where(Job.source_id == source_id, Job.source_job_id == source_job_id)
        )
