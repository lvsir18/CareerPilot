"""Candidate profile and job preferences (one row per user)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.types import JSONType

if TYPE_CHECKING:
    from app.db.models.user import User


class CandidateProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    headline: Mapped[str | None] = mapped_column(String(200))
    skills_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    education_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    experiences_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    projects_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="profile")


class JobPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_preferences"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    cities_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    job_types_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    keywords_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    excluded_keywords_json: Mapped[list[str]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    target_companies_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    target_roles_json: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    available_start_date: Mapped[str | None] = mapped_column(String(32))
    internship_duration_months: Mapped[int | None] = mapped_column(Integer)
    internship_days_per_week: Mapped[int | None] = mapped_column(Integer)
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    remote_ok: Mapped[bool | None] = mapped_column(Boolean)

    user: Mapped[User] = relationship(back_populates="preferences")
