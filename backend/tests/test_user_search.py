from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.user import User
from app.services.job_discovery_service import JobDiscoveryService
from app.services.user_search_service import UserSearchSettingsService, shares_server_search_key
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user


def _user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _prepared(settings: Settings, monkeypatch) -> Settings:
    monkeypatch.setattr(settings, "mailbox_secret_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-server-key")
    monkeypatch.setattr(settings, "search_provider", "tavily")
    monkeypatch.setattr(settings, "shared_search_key_admins_only", True)
    return settings


def test_saved_search_key_is_masked(db_session: Session, settings: Settings, monkeypatch):
    settings = _prepared(settings, monkeypatch)
    user = _user(db_session, "search-mask@example.com")
    service = UserSearchSettingsService(db_session, settings)

    described = service.upsert(user, api_key="tvly-abcdefgh12345678")

    assert described["configured"] is True
    assert described["masked_key"] == "tvly…5678"
    assert "abcdefgh" not in str(described)
    assert service.resolve(user.id) == "tvly-abcdefgh12345678"


def test_server_key_is_shared_with_admins_only(settings: Settings, monkeypatch):
    settings = _prepared(settings, monkeypatch)
    admin = User(email="admin@example.com", password_hash="x")
    plain = User(email="plain@example.com", password_hash="x")

    assert shares_server_search_key(settings, admin) is True
    assert shares_server_search_key(settings, plain) is False


def test_discovery_prefers_the_account_key(db_session: Session, settings: Settings, monkeypatch):
    settings = _prepared(settings, monkeypatch)
    user = _user(db_session, "search-own@example.com")
    UserSearchSettingsService(db_session, settings).upsert(user, api_key="tvly-own-key")
    service = JobDiscoveryService(db_session, settings)

    searcher, temporary = service._search_for(user.id)

    assert temporary is True
    assert searcher._providers[0]._key == "tvly-own-key"  # type: ignore[attr-defined]
    searcher.close()


def test_non_admin_without_key_gets_no_live_search(
    db_session: Session, settings: Settings, monkeypatch
):
    settings = _prepared(settings, monkeypatch)
    user = _user(db_session, "search-nokey@example.com")
    service = JobDiscoveryService(db_session, settings)

    searcher, temporary = service._search_for(user.id)

    assert temporary is True
    # Provider exists but is unconfigured: it will not spend the owner's quota.
    assert searcher._providers[0].configured is False  # type: ignore[attr-defined]
    searcher.close()


def test_admin_without_key_falls_back_to_the_server_searcher(
    db_session: Session, settings: Settings, monkeypatch
):
    settings = _prepared(settings, monkeypatch)
    admin = _user(db_session, "admin@example.com")
    service = JobDiscoveryService(db_session, settings)

    searcher, temporary = service._search_for(admin.id)

    assert temporary is False
    assert searcher is service._search


def test_llm_server_key_is_admin_only(db_session: Session, settings: Settings, monkeypatch):
    from app.agents.llm import resolve_chat_model

    _prepared(settings, monkeypatch)
    monkeypatch.setattr(settings, "llm_api_key", "server-llm-key")
    monkeypatch.setattr(settings, "llm_model", "server-model")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:9/v1")
    monkeypatch.setattr(settings, "shared_llm_key_admins_only", True)

    plain = _user(db_session, "llm-plain@example.com")
    admin = _user(db_session, "admin@example.com")

    assert resolve_chat_model(db_session, settings, plain) is None
    assert resolve_chat_model(db_session, settings, admin) is not None


def test_search_settings_api_round_trip(app: FastAPI, settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "mailbox_secret_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-server-key")

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="search-api@example.com")

        empty = client.get("/api/v1/settings/search").json()["data"]
        assert empty["configured"] is False
        assert empty["server_default_available"] is True

        saved = client.put("/api/v1/settings/search", json={"api_key": "tvly-api-12345678"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["data"]["masked_key"] == "tvly…5678"
        assert "12345678" not in saved.text

        cleared = client.delete("/api/v1/settings/search")
        assert cleared.status_code == 204
        assert client.get("/api/v1/settings/search").json()["data"]["configured"] is False


def test_search_test_endpoint_requires_a_key(app: FastAPI, settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "mailbox_secret_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "tavily_api_key", None)
    monkeypatch.setattr(settings, "shared_search_key_admins_only", True)

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="search-test@example.com")
        response = client.post("/api/v1/settings/search/test", json={"api_key": None})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SEARCH_KEY_REQUIRED"
