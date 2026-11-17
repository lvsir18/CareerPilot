"""Job source access layer."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.job import JobSource


class JobSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> list[JobSource]:
        return list(self._session.scalars(select(JobSource).order_by(JobSource.created_at)))

    def get(self, source_id: UUID) -> JobSource | None:
        return self._session.get(JobSource, source_id)

    def get_by_key(self, source_type: str, source_key: str) -> JobSource | None:
        return self._session.scalar(
            select(JobSource).where(
                JobSource.source_type == source_type,
                JobSource.source_key == source_key,
            )
        )
