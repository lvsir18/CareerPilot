"""m2r2 application progress imports

Revision ID: dd74cd7fdcc4
Revises: c26e98821289
Create Date: 2026-10-21 18:19:42.004620
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "dd74cd7fdcc4"
down_revision: str | None = "c26e98821289"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = (
    "'to_apply', 'preparing', 'applied', 'online_assessment', 'interview', "
    "'offer', 'rejected', 'withdrawn', 'closed', 'unknown'"
)
NEW_STATUSES = (
    "'saved', 'planned', 'to_apply', 'preparing', 'applied', 'screening', "
    "'assessment', 'online_assessment', 'interview', 'offer', 'rejected', "
    "'withdrawn', 'closed', 'unknown'"
)
SOURCE_TYPES = "'manual', 'email_import', 'official_api', 'browser_assisted'"
VERIFICATION = (
    "'user_reported', 'email_confirmed', 'website_user_confirmed', 'official_api', 'unverified'"
)


def upgrade() -> None:
    op.create_table(
        "application_imports",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("sender", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_company", sa.String(length=200), nullable=True),
        sa.Column("parsed_title", sa.String(length=300), nullable=True),
        sa.Column(
            "parsed_status",
            sa.Enum(
                "saved",
                "planned",
                "to_apply",
                "preparing",
                "applied",
                "screening",
                "assessment",
                "online_assessment",
                "interview",
                "offer",
                "rejected",
                "withdrawn",
                "closed",
                "unknown",
                name="application_import_parsed_status",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("parsed_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("matched_application_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_event_id", sa.Uuid(), nullable=True),
        sa.Column("body_excerpt", sa.Text(), nullable=True),
        sa.Column(
            "warnings_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('ready', 'needs_review', 'confirmed', 'discarded')",
            name=op.f("ck_application_imports_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_event_id"],
            ["application_events.id"],
            name=op.f("fk_application_imports_confirmed_event_id_application_events"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["matched_application_id"],
            ["applications.id"],
            name=op.f("fk_application_imports_matched_application_id_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_application_imports_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_imports")),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_application_imports_user_hash"),
    )
    op.create_index(
        "ix_application_imports_user_created",
        "application_imports",
        ["user_id", "created_at"],
        unique=False,
    )

    # Add columns with temporary defaults so existing M1 data upgrades cleanly.
    op.add_column(
        "application_events",
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "application_events",
        sa.Column("source_type", sa.String(length=32), server_default="manual", nullable=False),
    )
    op.add_column("application_events", sa.Column("source_reference", sa.String(length=200)))
    op.add_column("application_events", sa.Column("evidence_summary", sa.Text()))
    op.add_column(
        "application_events",
        sa.Column(
            "verification_status",
            sa.String(length=32),
            server_default="user_reported",
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE application_events SET event_time = created_at, "
        "source_type = CASE WHEN evidence_type IN ('manual', 'email_import', "
        "'official_api', 'browser_assisted') THEN evidence_type ELSE 'manual' END"
    )
    op.create_index(
        "ix_application_events_application_time",
        "application_events",
        ["application_id", "event_time"],
        unique=False,
    )
    op.create_index(
        "uq_application_events_source_ref",
        "application_events",
        ["application_id", "source_type", "source_reference"],
        unique=True,
        postgresql_where=sa.text("source_reference IS NOT NULL"),
    )

    op.add_column("applications", sa.Column("job_lead_id", sa.Uuid(), nullable=True))
    op.add_column("applications", sa.Column("external_company", sa.String(length=200)))
    op.add_column("applications", sa.Column("external_title", sa.String(length=300)))
    op.add_column("applications", sa.Column("external_url", sa.String(length=1000)))
    op.add_column("applications", sa.Column("last_confirmed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "applications",
        sa.Column("source_type", sa.String(length=32), server_default="manual", nullable=False),
    )
    op.add_column("applications", sa.Column("source_reference", sa.String(length=200)))
    op.add_column("applications", sa.Column("dedupe_key", sa.String(length=100)))

    op.execute(
        "UPDATE applications a SET external_company = c.name, "
        "external_title = j.title, external_url = j.source_url, "
        "last_confirmed_at = COALESCE(a.last_confirmed_at, a.applied_at, a.created_at), "
        "dedupe_key = 'job:' || a.job_id::text "
        "FROM jobs j JOIN companies c ON c.id = j.company_id "
        "WHERE j.id = a.job_id AND a.dedupe_key IS NULL"
    )
    # Defensive fallback for any row with a missing job (should not exist in M1).
    op.execute(
        "UPDATE applications SET dedupe_key = 'legacy:' || id::text WHERE dedupe_key IS NULL"
    )
    op.alter_column("applications", "dedupe_key", existing_type=sa.String(100), nullable=False)
    op.alter_column(
        "applications",
        "job_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )

    op.drop_constraint("status_valid", "applications", type_="check")
    op.drop_constraint("from_status_valid", "application_events", type_="check")
    op.drop_constraint("to_status_valid", "application_events", type_="check")
    op.create_check_constraint("status_valid", "applications", f"status IN ({NEW_STATUSES})")
    op.create_check_constraint(
        "from_status_valid",
        "application_events",
        f"from_status IS NULL OR from_status IN ({NEW_STATUSES})",
    )
    op.create_check_constraint(
        "to_status_valid", "application_events", f"to_status IN ({NEW_STATUSES})"
    )
    op.create_check_constraint(
        "source_type_valid", "applications", f"source_type IN ({SOURCE_TYPES})"
    )
    op.create_check_constraint(
        "source_type_valid", "application_events", f"source_type IN ({SOURCE_TYPES})"
    )
    op.create_check_constraint(
        "verification_status_valid",
        "application_events",
        f"verification_status IN ({VERIFICATION})",
    )
    op.create_check_constraint(
        "application_target_required",
        "applications",
        "job_id IS NOT NULL OR job_lead_id IS NOT NULL OR external_url IS NOT NULL",
    )
    op.create_check_constraint(
        "external_url_http",
        "applications",
        "external_url IS NULL OR external_url ~ '^https?://'",
    )
    op.create_index(
        "ix_applications_user_updated",
        "applications",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_applications_user_dedupe", "applications", ["user_id", "dedupe_key"]
    )
    op.create_foreign_key(
        op.f("fk_applications_job_lead_id_job_leads"),
        "applications",
        "job_leads",
        ["job_lead_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_applications_job_lead_id_job_leads"), "applications", type_="foreignkey"
    )
    op.drop_constraint("uq_applications_user_dedupe", "applications", type_="unique")
    op.drop_index("ix_applications_user_updated", table_name="applications")
    op.drop_constraint("external_url_http", "applications", type_="check")
    op.drop_constraint("application_target_required", "applications", type_="check")
    op.drop_constraint("verification_status_valid", "application_events", type_="check")
    op.drop_constraint("source_type_valid", "application_events", type_="check")
    op.drop_constraint("source_type_valid", "applications", type_="check")
    op.drop_constraint("to_status_valid", "application_events", type_="check")
    op.drop_constraint("from_status_valid", "application_events", type_="check")
    op.drop_constraint("status_valid", "applications", type_="check")
    op.create_check_constraint("status_valid", "applications", f"status IN ({OLD_STATUSES})")
    op.create_check_constraint(
        "from_status_valid",
        "application_events",
        f"from_status IS NULL OR from_status IN ({OLD_STATUSES})",
    )
    op.create_check_constraint(
        "to_status_valid", "application_events", f"to_status IN ({OLD_STATUSES})"
    )
    op.alter_column(
        "applications",
        "job_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_column("applications", "dedupe_key")
    op.drop_column("applications", "source_reference")
    op.drop_column("applications", "source_type")
    op.drop_column("applications", "last_confirmed_at")
    op.drop_column("applications", "external_url")
    op.drop_column("applications", "external_title")
    op.drop_column("applications", "external_company")
    op.drop_column("applications", "job_lead_id")
    op.drop_index(
        "uq_application_events_source_ref",
        table_name="application_events",
        postgresql_where=sa.text("source_reference IS NOT NULL"),
    )
    op.drop_index("ix_application_events_application_time", table_name="application_events")
    op.drop_column("application_events", "verification_status")
    op.drop_column("application_events", "evidence_summary")
    op.drop_column("application_events", "source_reference")
    op.drop_column("application_events", "source_type")
    op.drop_column("application_events", "event_time")
    op.drop_index("ix_application_imports_user_created", table_name="application_imports")
    op.drop_table("application_imports")
