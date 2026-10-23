from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import make_url

from alembic import command as alembic_command
from tests.conftest import BACKEND_DIR, TEST_DATABASE_URL

CORE_TABLES = {
    "users",
    "user_sessions",
    "candidate_profiles",
    "job_preferences",
    "companies",
    "job_sources",
    "jobs",
    "saved_jobs",
    "applications",
    "application_events",
    "sync_runs",
    "external_account_connections",
    "job_leads",
    "source_evidence",
    "application_imports",
}


def _alembic_config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    return config


def _tables(url: str) -> set[str]:
    with (
        psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://")) as conn,
        conn.cursor() as cursor,
    ):
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.integration
def test_migrations_upgrade_downgrade_and_reapply() -> None:
    parsed = make_url(TEST_DATABASE_URL)
    database = f"careerpilot_migration_{uuid4().hex[:8]}"
    admin_dsn = (
        f"postgresql://{parsed.username}:{parsed.password}@{parsed.host}:{parsed.port}/postgres"
    )
    db_url = TEST_DATABASE_URL.replace(parsed.database or "", database)

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{database}"')
    try:
        config = _alembic_config(db_url)
        alembic_command.upgrade(config, "head")
        # Running upgrade again must be a no-op, not an error.
        alembic_command.upgrade(config, "head")
        assert _tables(db_url) >= CORE_TABLES

        alembic_command.downgrade(config, "base")
        remaining = _tables(db_url)
        assert not (CORE_TABLES & remaining)

        alembic_command.upgrade(config, "head")
        assert _tables(db_url) >= CORE_TABLES
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
