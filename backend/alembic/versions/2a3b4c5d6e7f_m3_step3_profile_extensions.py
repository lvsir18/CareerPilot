"""m3 step3 profile extensions

Revision ID: 2a3b4c5d6e7f
Revises: 1f3a4b5c6d7e
Create Date: 2026-10-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2a3b4c5d6e7f"
down_revision: str | None = "1f3a4b5c6d7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "experiences_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_preferences",
        sa.Column(
            "target_roles_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "job_preferences",
        sa.Column("available_start_date", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "job_preferences",
        sa.Column("internship_duration_months", sa.Integer(), nullable=True),
    )
    op.add_column(
        "job_preferences",
        sa.Column("internship_days_per_week", sa.Integer(), nullable=True),
    )
    op.add_column(
        "job_preferences",
        sa.Column("graduation_year", sa.Integer(), nullable=True),
    )
    op.add_column(
        "job_preferences",
        sa.Column("remote_ok", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_preferences", "remote_ok")
    op.drop_column("job_preferences", "graduation_year")
    op.drop_column("job_preferences", "internship_days_per_week")
    op.drop_column("job_preferences", "internship_duration_months")
    op.drop_column("job_preferences", "available_start_date")
    op.drop_column("job_preferences", "target_roles_json")
    op.drop_column("candidate_profiles", "confirmed_at")
    op.drop_column("candidate_profiles", "content_hash")
    op.drop_column("candidate_profiles", "experiences_json")
