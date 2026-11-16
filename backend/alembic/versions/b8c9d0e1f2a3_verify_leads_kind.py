"""m2r10: allow the ``verify_leads`` maintenance kind

Verifying every pending candidate of a company runs in the worker (no
per-minute limiter), and it reuses the maintenance run table so the UI gets
progress, cancel and the sidebar activity marker for free.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = op.f("ck_job_maintenance_runs_kind_valid")

_OLD = "kind IN ('refresh', 'discover', 'prune')"
_NEW = "kind IN ('refresh', 'discover', 'prune', 'verify_leads')"


def upgrade() -> None:
    op.drop_constraint(_NAME, "job_maintenance_runs", type_="check")
    op.create_check_constraint(_NAME, "job_maintenance_runs", _NEW)


def downgrade() -> None:
    op.drop_constraint(_NAME, "job_maintenance_runs", type_="check")
    op.create_check_constraint(_NAME, "job_maintenance_runs", _OLD)
