"""Sync run access layer."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.enums import SyncStatus
from app.db.models.sync_run import SyncRun


class SyncRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: SyncRun) -> None:
        self._session.add(run)

    def get(self, run_id: UUID) -> SyncRun | None:
        return self._session.get(SyncRun, run_id)

    def get_for_update(self, run_id: UUID) -> SyncRun | None:
        return self._session.scalar(select(SyncRun).where(SyncRun.id == run_id).with_for_update())

    def list(self, *, page: int, page_size: int) -> tuple[list[SyncRun], int]:
        total = self._session.scalar(select(func.count(SyncRun.id))) or 0
        stmt = (
            select(SyncRun)
            .order_by(SyncRun.created_at.desc(), SyncRun.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._session.scalars(stmt).all()), int(total)

    def active_for_source(self, source_id: UUID) -> SyncRun | None:
        return self._session.scalar(
            select(SyncRun)
            .where(
                SyncRun.source_id == source_id,
                SyncRun.status.in_([SyncStatus.QUEUED, SyncStatus.RUNNING]),
            )
            .order_by(SyncRun.created_at.desc())
            .limit(1)
        )
