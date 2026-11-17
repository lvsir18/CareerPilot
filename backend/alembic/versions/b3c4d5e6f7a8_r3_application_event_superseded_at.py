"""r3: let a rescheduled appointment stop occupying a calendar slot

Rescheduling used to insert a second appointment, so the calendar showed both
the old and the new time. ``superseded_at`` keeps the audit trail while removing
the replaced slot from future schedules.

Revision ID: b3c4d5e6f7a8
Revises: 8f9a0b1c2d3e
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "8f9a0b1c2d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_events",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_events", "superseded_at")
