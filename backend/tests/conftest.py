from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from alembic import command as alembic_command
from app.core.cache import get_redis
from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.security.rate_limit import LoginRateLimiter, get_login_rate_limiter

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://career:career_dev_only@localhost:5432/careerpilot_test",
)

_TRUNCATE_TABLES = (
    "application_events",
    "applications",
    "saved_jobs",
    "agent_run_events",
    "agent_runs",
    "agent_threads",
    "recruitment_event_candidates",
    "mailbox_sync_runs",
    "mailbox_sync_cursors",
    "mailbox_connections",
    "match_records",
    "resumes",
    "candidate_profiles",
    "job_preferences",
    "jobs",
    "companies",
    "job_sources",
    "user_sessions",
    "users",
)


def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    database = parsed.database
    assert database and database != "postgres"
    admin_engine = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        admin_engine.dispose()


def _reset_schema(url: str) -> None:
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def _migrate(url: str) -> None:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    alembic_command.upgrade(config, "head")


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Fresh test database with the real Alembic schema applied."""
    try:
        _ensure_database(TEST_DATABASE_URL)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.fail(
            "无法连接 PostgreSQL 测试数据库。请先运行 "
            "`docker compose up -d --wait postgres`，或设置 TEST_DATABASE_URL。"
            f" 原始错误: {exc}"
        )
    _reset_schema(TEST_DATABASE_URL)
    _migrate(TEST_DATABASE_URL)

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(db_engine: Engine) -> Iterator[None]:
    with db_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(_TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def session_factory(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def settings() -> Settings:
    """Deterministic test settings; never reads a developer's real .env."""
    return Settings(
        app_env="test",
        demo_mode=True,
        database_url=TEST_DATABASE_URL,
        redis_url="redis://localhost:6379/15",
        session_secret="test_only_secret",
        trust_proxy_headers=True,
        admin_emails="admin@example.com",
        search_provider="none",
        tavily_api_key=None,
        llm_api_key=None,
        llm_model=None,
        llm_base_url=None,
    )


def _build_app(settings: Settings, session_factory: sessionmaker[Session]) -> FastAPI:
    app = create_app(settings)

    def override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # Tests must not share production Redis counters; rate-limit tests inject
    # their own fakeredis-backed limiter explicitly.
    app.dependency_overrides[get_login_rate_limiter] = lambda: LoginRateLimiter(
        get_redis(),
        enabled=False,
        ip_attempts=1,
        ip_window_seconds=60,
        account_attempts=1,
        account_window_seconds=60,
    )
    return app


class AutoCsrfTestClient(TestClient):
    """TestClient that behaves like the browser client.

    Adds a trusted Origin and echoes the CSRF cookie for unsafe requests. Use a
    plain TestClient to exercise missing/invalid origin or token scenarios.
    """

    def __init__(self, app: FastAPI, settings: Settings) -> None:
        super().__init__(app, base_url="http://testserver")
        self._csrf_settings = settings

    def request(self, method, url, **kwargs):  # type: ignore[override]
        if method.upper() not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            headers = dict(kwargs.get("headers") or {})
            lower_keys = {key.lower() for key in headers}
            if "origin" not in lower_keys:
                headers["Origin"] = self._csrf_settings.frontend_base_url
            token = self.cookies.get(self._csrf_settings.csrf_cookie_name)
            header_name = self._csrf_settings.csrf_header_name
            if token and header_name.lower() not in lower_keys:
                headers[header_name] = token
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture
def app(settings: Settings, session_factory: sessionmaker[Session]) -> FastAPI:
    return _build_app(settings, session_factory)


@pytest.fixture
def client(app: FastAPI, settings: Settings) -> Iterator[TestClient]:
    with AutoCsrfTestClient(app, settings) as test_client:
        yield test_client


@pytest.fixture
def plain_client(app: FastAPI) -> Iterator[TestClient]:
    """No automatic Origin/CSRF headers (for negative security tests)."""
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture
def non_demo_app(settings: Settings, session_factory: sessionmaker[Session]) -> FastAPI:
    """A production-like mode where demo fixtures must be invisible."""
    return _build_app(settings.model_copy(update={"demo_mode": False}), session_factory)


@pytest.fixture
def non_demo_client(non_demo_app: FastAPI, settings: Settings) -> Iterator[TestClient]:
    with AutoCsrfTestClient(non_demo_app, settings) as test_client:
        yield test_client
