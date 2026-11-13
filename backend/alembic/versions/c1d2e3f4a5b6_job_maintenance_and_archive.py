"""m2r4: soft archive for jobs and persisted maintenance runs

The job library needs a maintenance workflow: re-check an existing posting
against its official page, discover new postings from wired companies, and
archive postings that are provably closed.

Archiving is a soft delete (``archived_at``) so saved jobs, applications,
match history and the source link stay intact. ``job_maintenance_runs`` records
each user-triggered batch so the UI can show progress after a reload.

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("archived_by_user_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("jobs", sa.Column("archive_reason", sa.String(length=200), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("archive_evidence_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_foreign_key(
        "fk_jobs_archived_by_user_id_users",
        "jobs",
        "users",
        ["archived_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_archived_at", "jobs", ["archived_at"])

    op.create_table(
        "job_maintenance_runs",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("options_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("progress_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('refresh', 'discover', 'prune')", name="kind_valid"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'partial', 'failed', 'cancelled')",
            name="status_valid",
        ),
    )
    op.create_index(
        "ix_job_maintenance_runs_user_created",
        "job_maintenance_runs",
        ["user_id", "created_at"],
    )
    op.create_index("ix_job_maintenance_runs_status", "job_maintenance_runs", ["status"])
    op.create_index(
        "ix_job_maintenance_runs_dedupe", "job_maintenance_runs", ["dedupe_key", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_maintenance_runs_dedupe", table_name="job_maintenance_runs")
    op.drop_index("ix_job_maintenance_runs_status", table_name="job_maintenance_runs")
    op.drop_index("ix_job_maintenance_runs_user_created", table_name="job_maintenance_runs")
    op.drop_table("job_maintenance_runs")
    op.drop_index("ix_jobs_archived_at", table_name="jobs")
    op.drop_constraint("fk_jobs_archived_by_user_id_users", "jobs", type_="foreignkey")
    op.drop_column("jobs", "archive_evidence_json")
    op.drop_column("jobs", "archive_reason")
    op.drop_column("jobs", "archived_by_user_id")
    op.drop_column("jobs", "archived_at")
