from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import PLACEHOLDER_SECRET, Settings


def test_development_defaults_allow_demo_without_credentials() -> None:
    settings = Settings(app_env="development")

    assert settings.demo_mode is True
    assert settings.llm_configured is False
    assert settings.execution_mode == "rule_fallback"
    assert settings.allowed_origins == [settings.frontend_base_url]


def test_production_rejects_sample_secret() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env="production", demo_mode=False, session_secret=PLACEHOLDER_SECRET)

    assert "SESSION_SECRET" in str(exc_info.value)


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", demo_mode=False, session_secret="too-short")


def test_production_rejects_demo_mode() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env="production", demo_mode=True, session_secret="x" * 40)

    assert "DEMO_MODE" in str(exc_info.value)


def test_production_accepts_safe_configuration() -> None:
    settings = Settings(app_env="production", demo_mode=False, session_secret="x" * 40)

    assert settings.is_production is True
    assert settings.execution_mode == "rule_fallback"


def test_llm_requires_url_key_and_model() -> None:
    partial = Settings(app_env="test", llm_api_key="key", llm_model="model")

    assert partial.llm_configured is False
    assert partial.execution_mode == "rule_fallback"


def test_cors_origins_override_frontend_url() -> None:
    settings = Settings(
        app_env="test",
        frontend_base_url="http://localhost:3000",
        cors_origins=["https://careerpilot.example.com"],
    )

    assert settings.allowed_origins == ["https://careerpilot.example.com"]
