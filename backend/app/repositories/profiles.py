"""Profile and preference access layer."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.profile import CandidateProfile, JobPreference


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_profile(self, user_id: UUID) -> CandidateProfile | None:
        return self._session.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == user_id)
        )

    def get_preferences(self, user_id: UUID) -> JobPreference | None:
        return self._session.scalar(select(JobPreference).where(JobPreference.user_id == user_id))

    def add(self, row: CandidateProfile | JobPreference) -> None:
        self._session.add(row)
