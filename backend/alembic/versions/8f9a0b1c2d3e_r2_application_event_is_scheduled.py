"""r2: mark application events that represent a real appointment

``application_events.event_time`` is filled with "now" when a status changes, so
it cannot distinguish "recorded at" from "scheduled for". The calendar needs the
latter only.

Revision ID: 8f9a0b1c2d3e
Revises: 6e7f8a9b0c1d
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8f9a0b1c2d3e"
down_revision: str | None = "6e7f8a9b0c1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_events",
        sa.Column(
            "is_scheduled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("application_events", "is_scheduled")
