"""Match-result cache access layer (always scoped by user)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.match_record import MatchRecord


class MatchRecordRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(
        self,
        *,
        user_id: UUID,
        job_id: UUID | None,
        job_lead_id: UUID | None,
        profile_version: int,
        scorer_version: str,
        job_content_hash: str | None,
    ) -> MatchRecord | None:
        return self._session.scalar(
            select(MatchRecord).where(
                MatchRecord.user_id == user_id,
                MatchRecord.job_id == job_id,
                MatchRecord.job_lead_id == job_lead_id,
                MatchRecord.profile_version == profile_version,
                MatchRecord.scorer_version == scorer_version,
                MatchRecord.job_content_hash == job_content_hash,
            )
        )

    def add(self, record: MatchRecord) -> None:
        self._session.add(record)
