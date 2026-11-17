"""m2a job source check constraints

Revision ID: bcf5c204d698
Revises: 0300e178f30b
Create Date: 2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "bcf5c204d698"
down_revision: str | None = "0300e178f30b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "source_method_valid",
        "jobs",
        "source_method IN ('api', 'public_page', 'manual_import', 'manual_paste', "
        "'fixture', 'unknown')",
    )
    op.create_check_constraint(
        "verification_status_valid",
        "jobs",
        "verification_status IN ('verified', 'user_confirmed', 'unverified', 'stale')",
    )


def downgrade() -> None:
    # Alembic applies the project naming convention to these unprefixed names.
    op.drop_constraint("verification_status_valid", "jobs", type_="check")
    op.drop_constraint("source_method_valid", "jobs", type_="check")
