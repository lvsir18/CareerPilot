"""m51 mailbox connections, cursors, runs and recruitment candidates

Revision ID: 5d6e7f8a9b0c
Revises: 4c5d6e7f8a9b
Create Date: 2026-10-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5d6e7f8a9b0c"
down_revision: str | None = "4c5d6e7f8a9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "mailbox_connections",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("provider IN ('qq_imap', 'gmail')", name="mailbox_provider_valid"),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'revoked', 'error')",
            name="mailbox_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mailbox_connections_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailbox_connections")),
        sa.UniqueConstraint(
            "user_id", "provider", "email_address", name="uq_mailbox_user_provider_email"
        ),
    )
    op.create_index("ix_mailbox_user_status", "mailbox_connections", ["user_id", "status"])

    op.create_table(
        "mailbox_sync_cursors",
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("folder", sa.String(length=100), nullable=False),
        sa.Column("gmail_history_id", sa.String(length=64), nullable=True),
        sa.Column("imap_uidvalidity", sa.Integer(), nullable=True),
        sa.Column("imap_last_uid", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["mailbox_connections.id"],
            name=op.f("fk_mailbox_sync_cursors_connection_id_mailbox_connections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailbox_sync_cursors")),
        sa.UniqueConstraint("connection_id", "folder", name="uq_mailbox_cursor_folder"),
    )

    op.create_table(
        "mailbox_sync_runs",
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scanned_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="mailbox_sync_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["mailbox_connections.id"],
            name=op.f("fk_mailbox_sync_runs_connection_id_mailbox_connections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailbox_sync_runs")),
    )
    op.create_index(
        "ix_mailbox_sync_runs_connection", "mailbox_sync_runs", ["connection_id", "created_at"]
    )

    op.create_table(
        "recruitment_event_candidates",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("message_reference", sa.String(length=200), nullable=False),
        sa.Column("matched_application_id", sa.Uuid(), nullable=True),
        sa.Column("parsed_company", sa.String(length=200), nullable=True),
        sa.Column("parsed_title", sa.String(length=300), nullable=True),
        sa.Column("parsed_status", sa.String(length=32), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("conflict_kind", sa.String(length=32), nullable=False),
        sa.Column("conflict_reason", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "review_status IN ('pending', 'conflict', 'confirmed', 'discarded')",
            name="candidate_review_status_valid",
        ),
        sa.CheckConstraint(
            "conflict_kind IN ('none', 'duplicate', 'out_of_order', 'ambiguous_match', "
            "'status_conflict', 'missing_information')",
            name="candidate_conflict_kind_valid",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["mailbox_connections.id"],
            name=op.f("fk_recruitment_event_candidates_connection_id_mailbox_connections"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["matched_application_id"],
            ["applications.id"],
            name=op.f("fk_recruitment_event_candidates_matched_application_id_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recruitment_event_candidates_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recruitment_event_candidates")),
        sa.UniqueConstraint(
            "user_id", "provider", "message_reference", name="uq_recruitment_candidate_message"
        ),
    )
    op.create_index(
        "ix_recruitment_candidates_user_status",
        "recruitment_event_candidates",
        ["user_id", "review_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recruitment_candidates_user_status", table_name="recruitment_event_candidates"
    )
    op.drop_table("recruitment_event_candidates")
    op.drop_index("ix_mailbox_sync_runs_connection", table_name="mailbox_sync_runs")
    op.drop_table("mailbox_sync_runs")
    op.drop_table("mailbox_sync_cursors")
    op.drop_index("ix_mailbox_user_status", table_name="mailbox_connections")
    op.drop_table("mailbox_connections")
