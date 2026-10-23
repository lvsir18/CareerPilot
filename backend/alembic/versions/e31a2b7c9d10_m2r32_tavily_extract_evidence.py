"""m2r32 tavily extract evidence method

Revision ID: e31a2b7c9d10
Revises: dd74cd7fdcc4
Create Date: 2026-10-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e31a2b7c9d10"
down_revision: str | None = "dd74cd7fdcc4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "verification_method_valid"


def upgrade() -> None:
    op.add_column(
        "job_leads",
        sa.Column("last_verification_error", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "job_leads",
        sa.Column(
            "last_verification_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.drop_constraint(_NAME, "source_evidence", type_="check")
    op.create_check_constraint(
        _NAME,
        "source_evidence",
        "verification_method IN ('search_provider', 'official_list_page', "
        "'public_page_parse', 'tavily_extract', 'user_confirmed', 'none')",
    )


def downgrade() -> None:
    op.drop_constraint(_NAME, "source_evidence", type_="check")
    op.drop_column("job_leads", "last_verification_attempt_at")
    op.drop_column("job_leads", "last_verification_error")
    op.create_check_constraint(
        _NAME,
        "source_evidence",
        "verification_method IN ('search_provider', 'official_list_page', "
        "'public_page_parse', 'user_confirmed', 'none')",
    )
