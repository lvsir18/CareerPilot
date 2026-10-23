from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__


def test_system_info_exposes_runtime_mode_without_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == __version__
    assert body["demo_mode"] is True
    assert body["execution_mode"] == "rule_fallback"
    assert body["llm_configured"] is False
    assert body["public_connectors_enabled"] is False
    assert body["api_docs_url"].endswith("/docs")

    serialized = response.text.lower()
    for secret_key in ("session_secret", "llm_api_key", "password"):
        assert secret_key not in serialized


def test_system_info_reports_llm_mode_when_configured() -> None:
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(
        app_env="test",
        demo_mode=False,
        llm_base_url="https://llm.example.com/v1",
        llm_api_key="test-key",
        llm_model="test-model",
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/v1/system/info").json()

    assert body["execution_mode"] == "llm"
    assert body["llm_configured"] is True
    assert "test-key" not in str(body)
