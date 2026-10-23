"""Saved job / to-apply list service with idempotent writes."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.enums import SavedListType
from app.db.models.saved_job import SavedJob
from app.db.models.user import User
from app.repositories.saved_jobs import SavedJobRepository
from app.services.job_service import JobService


class SavedJobService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repository = SavedJobRepository(session)
        self._jobs = JobService(session, settings)

    def save(
        self,
        user: User,
        job_id: UUID,
        list_type: SavedListType,
        note: str | None,
    ) -> tuple[SavedJob, bool]:
        self._jobs.get_job(job_id)  # 404 when missing or demo hidden

        existing = self._repository.get(user.id, job_id, list_type)
        if existing is not None:
            if note is not None and note != existing.note:
                existing.note = note
                self._session.commit()
                self._session.refresh(existing)
            return existing, False

        row = SavedJob(user_id=user.id, job_id=job_id, list_type=list_type, note=note)
        self._repository.add(row)
        try:
            self._session.commit()
        except IntegrityError:
            # Concurrent duplicate insert: unique(user_id, job_id, list_type).
            self._session.rollback()
            existing = self._repository.get(user.id, job_id, list_type)
            if existing is None:
                raise AppError(
                    code="SAVED_JOB_CONFLICT",
                    message="收藏写入冲突，请重试",
                    status_code=409,
                ) from None
            return existing, False

        self._session.refresh(row)
        return row, True

    def remove(self, user: User, job_id: UUID, list_type: SavedListType) -> bool:
        row = self._repository.get(user.id, job_id, list_type)
        if row is None:
            return False
        self._repository.delete(row)
        self._session.commit()
        return True

    def list(
        self,
        user: User,
        *,
        list_type: SavedListType | None,
        page: int,
        page_size: int,
    ) -> tuple[list[SavedJob], int]:
        return self._repository.list(
            user.id,
            list_type=list_type,
            page=page,
            page_size=page_size,
            include_demo=self._settings.demo_mode,
        )
