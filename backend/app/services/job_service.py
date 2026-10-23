"""Job listing/detail domain service."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.job import Job
from app.repositories.jobs import JobQuery, JobRepository


class JobService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._repository = JobRepository(session)
        self._settings = settings

    def list_jobs(self, query: JobQuery) -> tuple[list[Job], int]:
        # Production never leaks demo fixtures into real listings.
        scoped = replace(query, include_demo=self._settings.demo_mode)
        return self._repository.list(scoped)

    def get_job(self, job_id: UUID) -> Job:
        job = self._repository.get(job_id, include_demo=self._settings.demo_mode)
        if job is None:
            raise AppError(
                code="JOB_NOT_FOUND",
                message="岗位不存在或已不可见",
                status_code=404,
            )
        return job
