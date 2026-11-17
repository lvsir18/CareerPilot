from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.user import User
from app.services.user_llm_service import UserLlmSettingsService
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user


def _user(session: Session, email: str = "llm-owner@example.com") -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _settings_with_key(settings: Settings, monkeypatch) -> Settings:
    monkeypatch.setattr(settings, "mailbox_secret_key", Fernet.generate_key().decode())
    return settings


def test_saved_key_is_masked_and_resolvable(db_session: Session, settings: Settings, monkeypatch):
    settings = _settings_with_key(settings, monkeypatch)
    user = _user(db_session)
    service = UserLlmSettingsService(db_session, settings)

    described = service.upsert(
        user,
        provider="openai",
        api_key="sk-test-1234567890abcd",
        base_url="https://gateway.example.com/v1",
        model="deepseek-chat",
    )

    assert described["configured"] is True
    assert described["key_set"] is True
    assert described["masked_key"] == "sk-t…abcd"
    assert "1234567890" not in str(described)  # never echo the secret

    resolved = service.resolve(user.id)
    assert resolved is not None
    assert resolved.api_key == "sk-test-1234567890abcd"
    assert resolved.provider == "openai"
    assert resolved.model == "deepseek-chat"
    assert resolved.base_url == "https://gateway.example.com/v1"


def test_anthropic_default_model_is_applied(db_session: Session, settings: Settings, monkeypatch):
    settings = _settings_with_key(settings, monkeypatch)
    user = _user(db_session, "llm-anthropic@example.com")
    service = UserLlmSettingsService(db_session, settings)

    service.upsert(user, provider="anthropic", api_key="sk-ant-123456", base_url=None, model=None)

    resolved = service.resolve(user.id)
    assert resolved is not None
    assert resolved.provider == "anthropic"
    assert resolved.model == "claude-3-5-sonnet-latest"


def test_first_save_requires_a_key(db_session: Session, settings: Settings, monkeypatch):
    from app.core.errors import AppError

    settings = _settings_with_key(settings, monkeypatch)
    user = _user(db_session, "llm-nokey@example.com")
    service = UserLlmSettingsService(db_session, settings)

    try:
        service.upsert(user, provider="openai", api_key=None, base_url=None, model=None)
    except AppError as exc:
        assert exc.code == "API_KEY_REQUIRED"
    else:  # pragma: no cover
        raise AssertionError("expected API_KEY_REQUIRED")


def test_invalid_provider_is_rejected(db_session: Session, settings: Settings, monkeypatch):
    from app.core.errors import AppError

    settings = _settings_with_key(settings, monkeypatch)
    user = _user(db_session, "llm-badprovider@example.com")
    service = UserLlmSettingsService(db_session, settings)

    try:
        service.upsert(user, provider="gemini", api_key="x", base_url=None, model=None)
    except AppError as exc:
        assert exc.code == "INVALID_PROVIDER"
    else:  # pragma: no cover
        raise AssertionError("expected INVALID_PROVIDER")


def test_accounts_do_not_share_credentials(db_session: Session, settings: Settings, monkeypatch):
    settings = _settings_with_key(settings, monkeypatch)
    service = UserLlmSettingsService(db_session, settings)
    first = _user(db_session, "llm-a@example.com")
    second = _user(db_session, "llm-b@example.com")

    service.upsert(first, provider="openai", api_key="sk-a-12345678", base_url=None, model=None)

    assert service.describe(first.id)["configured"] is True
    assert service.describe(second.id)["configured"] is False
    # The second account falls back to the server default.
    assert service.resolve(second.id) is None


def test_clear_removes_the_override(db_session: Session, settings: Settings, monkeypatch):
    settings = _settings_with_key(settings, monkeypatch)
    user = _user(db_session, "llm-clear@example.com")
    service = UserLlmSettingsService(db_session, settings)
    service.upsert(user, provider="openai", api_key="sk-clear-1234", base_url=None, model=None)

    assert service.clear(user.id) is True
    assert service.resolve(user.id) is None
    assert service.describe(user.id)["configured"] is False


def test_undecryptable_key_falls_back_instead_of_crashing(
    db_session: Session, settings: Settings, monkeypatch
):
    settings = _settings_with_key(settings, monkeypatch)
    user = _user(db_session, "llm-broken@example.com")
    service = UserLlmSettingsService(db_session, settings)
    service.upsert(user, provider="openai", api_key="sk-broken-9999", base_url=None, model=None)

    row = service.get_row(user.id)
    row.api_key_encrypted = "not-a-valid-token"
    db_session.commit()

    assert service.resolve(user.id) is None


def test_api_masks_the_key_and_supports_clear(
    app: FastAPI, settings: Settings, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "mailbox_secret_key", Fernet.generate_key().decode())

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="llm-api@example.com")

        empty = client.get("/api/v1/settings/llm").json()["data"]
        assert empty["configured"] is False

        saved = client.put(
            "/api/v1/settings/llm",
            json={"provider": "openai", "api_key": "sk-api-1234567890", "model": "gpt-4o-mini"},
        )
        assert saved.status_code == 200, saved.text
        data = saved.json()["data"]
        assert data["masked_key"] == "sk-a…7890"
        assert "1234567890" not in saved.text

        cleared = client.delete("/api/v1/settings/llm")
        assert cleared.status_code == 204
        assert client.get("/api/v1/settings/llm").json()["data"]["configured"] is False


def test_resolved_provider_builds_the_matching_chat_model(settings: Settings) -> None:
    """OpenAI-compatible and Anthropic keys must produce different clients."""
    from app.agents.llm import build_user_chat_model
    from app.services.user_llm_service import LlmConfig

    openai_model = build_user_chat_model(
        LlmConfig(
            provider="openai",
            api_key="sk-openai-test",
            base_url="https://gateway.example.com/v1",
            model="gpt-4o-mini",
        ),
        settings,
    )
    anthropic_model = build_user_chat_model(
        LlmConfig(
            provider="anthropic",
            api_key="sk-ant-test",
            base_url=None,
            model="claude-3-5-sonnet-latest",
        ),
        settings,
    )

    assert openai_model.__class__.__name__ == "ChatOpenAI"
    assert anthropic_model.__class__.__name__ == "ChatAnthropic"
