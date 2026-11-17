"""m2r5: track the last successful status verification per job

``last_checked_at`` records every attempt, including ones that failed (timeout,
login wall). The re-check cooldown must only skip postings that were actually
verified recently, otherwise a failed check would be frozen for hours.

Revision ID: c2d3e4f5a6b7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_jobs_last_verified_at", "jobs", ["last_verified_at"])
    # Existing rows already carry a verification timestamp; seeding the new
    # column keeps the first maintenance run from re-checking the whole library.
    op.execute(
        "UPDATE jobs SET last_verified_at = verified_at "
        "WHERE last_verified_at IS NULL AND verified_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_last_verified_at", table_name="jobs")
    op.drop_column("jobs", "last_verified_at")
