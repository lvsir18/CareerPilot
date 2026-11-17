"""Saved job access layer (always scoped by user)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.enums import SavedListType
from app.db.models.job import Job
from app.db.models.saved_job import SavedJob


class SavedJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UUID, job_id: UUID, list_type: SavedListType) -> SavedJob | None:
        return self._session.scalar(
            select(SavedJob).where(
                SavedJob.user_id == user_id,
                SavedJob.job_id == job_id,
                SavedJob.list_type == list_type,
            )
        )

    def get_for_update(
        self, user_id: UUID, job_id: UUID, list_type: SavedListType
    ) -> SavedJob | None:
        return self._session.scalar(
            select(SavedJob)
            .where(
                SavedJob.user_id == user_id,
                SavedJob.job_id == job_id,
                SavedJob.list_type == list_type,
            )
            .with_for_update()
        )

    def list(
        self,
        user_id: UUID,
        *,
        list_type: SavedListType | None,
        page: int,
        page_size: int,
        include_demo: bool,
    ) -> tuple[list[SavedJob], int]:
        conditions = [SavedJob.user_id == user_id]
        if list_type is not None:
            conditions.append(SavedJob.list_type == list_type)
        if not include_demo:
            conditions.append(Job.is_demo.is_(False))

        total = self._session.scalar(
            select(func.count(SavedJob.id))
            .select_from(SavedJob)
            .join(Job, SavedJob.job_id == Job.id)
            .where(*conditions)
        )
        stmt = (
            select(SavedJob)
            .join(Job, SavedJob.job_id == Job.id)
            .where(*conditions)
            .order_by(SavedJob.created_at.desc(), SavedJob.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.scalars(stmt).all()), int(total or 0)

    def add(self, row: SavedJob) -> None:
        self._session.add(row)

    def delete(self, row: SavedJob) -> None:
        self._session.delete(row)
