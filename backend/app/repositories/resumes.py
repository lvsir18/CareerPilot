"""Resume access layer (always scoped by user)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.resume import Resume


class ResumeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UUID, resume_id: UUID) -> Resume | None:
        return self._session.scalar(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        )

    def list(self, user_id: UUID, *, limit: int) -> list[Resume]:
        stmt = (
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc(), Resume.id)
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())

    def count(self, user_id: UUID) -> int:
        return int(
            self._session.scalar(select(func.count(Resume.id)).where(Resume.user_id == user_id))
            or 0
        )

    def set_primary_false(self, user_id: UUID) -> None:
        for resume in self._session.scalars(select(Resume).where(Resume.user_id == user_id)).all():
            resume.is_primary = False

    def add(self, resume: Resume) -> None:
        self._session.add(resume)

    def delete(self, resume: Resume) -> None:
        self._session.delete(resume)
