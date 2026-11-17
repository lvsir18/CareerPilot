"""m3 step5 match records

Revision ID: 3b4c5d6e7f8a
Revises: 2a3b4c5d6e7f
Create Date: 2026-10-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3b4c5d6e7f8a"
down_revision: str | None = "2a3b4c5d6e7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_records",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("job_lead_id", sa.Uuid(), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("profile_content_hash", sa.String(length=64), nullable=False),
        sa.Column("job_content_hash", sa.String(length=64), nullable=True),
        sa.Column("scorer_version", sa.String(length=32), nullable=False),
        sa.Column("match_level", sa.String(length=16), nullable=False),
        sa.Column(
            "result_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "job_id IS NOT NULL OR job_lead_id IS NOT NULL",
            name=op.f("ck_match_records_match_target_required"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_match_records_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_lead_id"],
            ["job_leads.id"],
            name=op.f("fk_match_records_job_lead_id_job_leads"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_match_records_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_records")),
        sa.UniqueConstraint(
            "user_id",
            "job_id",
            "job_lead_id",
            "profile_version",
            "scorer_version",
            "job_content_hash",
            name="uq_match_records_key",
        ),
    )
    op.create_index("ix_match_records_user_created", "match_records", ["user_id", "created_at"])
    op.create_index("ix_match_records_job", "match_records", ["job_id"])
    op.create_index("ix_match_records_job_lead", "match_records", ["job_lead_id"])


def downgrade() -> None:
    op.drop_index("ix_match_records_job_lead", table_name="match_records")
    op.drop_index("ix_match_records_job", table_name="match_records")
    op.drop_index("ix_match_records_user_created", table_name="match_records")
    op.drop_table("match_records")
