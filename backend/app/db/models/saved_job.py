"""Saved job / to-apply list entries."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import SavedListType
from app.db.models.types import enum_column

if TYPE_CHECKING:
    from app.db.models.job import Job
    from app.db.models.user import User


class SavedJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", "list_type", name="uq_saved_jobs_user_job_list"),
        CheckConstraint("list_type IN ('saved', 'to_apply')", name="list_type_valid"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    list_type: Mapped[SavedListType] = mapped_column(
        enum_column(SavedListType, "saved_list_type", length=16),
        default=SavedListType.SAVED,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String(1000))

    user: Mapped[User] = relationship(back_populates="saved_jobs")
    job: Mapped[Job] = relationship(lazy="selectin")
