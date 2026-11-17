"""Agent conversation metadata (graph messages live in the LangGraph checkpointer)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentThread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_threads"
    __table_args__ = (Index("ix_agent_threads_user_created", "user_id", "created_at"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新对话")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
