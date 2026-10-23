from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models.enums import ExternalAuthMode, ExternalConnectionStatus
from app.db.models.external_account import ExternalAccountConnection
from app.db.models.user import User
from app.services.external_account_service import ExternalAccountService
from tests.conftest import AutoCsrfTestClient, _build_app
from tests.factories import register_user


def _user_id(session: Session, email: str):
    user = session.scalar(select(User).where(User.email == email))
    assert user is not None
    return user.id


def test_external_connection_is_user_scoped_and_revocable(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as user_a:
        register_user(user_a, email="ext-a@example.com")
        created = user_a.post(
            "/api/v1/external-accounts",
            json={
                "provider": "baidu",
                "auth_mode": "manual_import",
                "scopes": ["jobs:read"],
            },
        )
        assert created.status_code == 201
        connection_id = created.json()["data"]["id"]
        assert created.json()["data"]["secret_configured"] is False
        assert "secret_reference" not in created.json()["data"]

        listed = user_a.get("/api/v1/external-accounts")
        assert listed.status_code == 200
        assert len(listed.json()["data"]) == 1

    with AutoCsrfTestClient(app, settings) as user_b:
        register_user(user_b, email="ext-b@example.com")
        assert user_b.get("/api/v1/external-accounts").json()["data"] == []
        assert user_b.delete(f"/api/v1/external-accounts/{connection_id}").status_code == 404

    with AutoCsrfTestClient(app, settings) as user_a:
        # A new client has no cookies; log in rather than re-register.
        login = user_a.post(
            "/api/v1/auth/login",
            json={"email": "ext-a@example.com", "password": "strong-pass-123"},
        )
        assert login.status_code == 200
        revoked = user_a.delete(f"/api/v1/external-accounts/{connection_id}")
        assert revoked.status_code == 204
        listed = user_a.get("/api/v1/external-accounts").json()["data"]
        assert listed[0]["status"] == "revoked"


def test_external_connection_rejects_raw_secret(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="ext-secret@example.com")
        response = client.post(
            "/api/v1/external-accounts",
            json={
                "provider": "baidu",
                "auth_mode": "manual_import",
                "secret_reference": "Bearer raw-token-must-not-be-stored",
            },
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SECRET_REFERENCE_INVALID"


def test_browser_session_requires_explicit_allowlist(
    app: FastAPI,
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="ext-browser@example.com")
        denied = client.post(
            "/api/v1/external-accounts",
            json={
                "provider": "baidu",
                "auth_mode": "browser_session",
                "secret_reference": "vault://careerpilot/baidu/session",
            },
        )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "EXTERNAL_PROVIDER_NOT_AUTHORIZED"

    allowed_settings = settings.model_copy(
        update={
            "external_auth_allowed_providers": ["baidu"],
            "external_auth_allow_browser_session": True,
        }
    )
    allowed_app = _build_app(allowed_settings, session_factory)
    with AutoCsrfTestClient(allowed_app, allowed_settings) as client:
        register_user(client, email="ext-browser2@example.com")
        allowed = client.post(
            "/api/v1/external-accounts",
            json={
                "provider": "baidu",
                "auth_mode": "browser_session",
                "secret_reference": "vault://careerpilot/baidu/session",
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
    assert allowed.status_code == 201
    assert allowed.json()["data"]["auth_mode"] == "browser_session"
    assert allowed.json()["data"]["secret_configured"] is True


def test_expired_connection_clears_secret_reference(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="ext-expire@example.com")
        created = client.post(
            "/api/v1/external-accounts",
            json={
                "provider": "baidu",
                "auth_mode": "manual_import",
                "secret_reference": "vault://careerpilot/baidu/session",
            },
        )
        assert created.status_code == 201

    connection = db_session.scalar(select(ExternalAccountConnection))
    assert connection is not None
    connection.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    service = ExternalAccountService(db_session, settings)
    listed = service.list_for_user(connection.user_id)

    assert listed[0].status == ExternalConnectionStatus.EXPIRED
    assert listed[0].secret_reference is None
    assert service.active_for_user(connection.user_id, "baidu") is None


def test_connection_requires_secret_reference_for_authorized_modes(
    app: FastAPI, settings: Settings, db_session: Session
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        registered = register_user(client, email="ext-noref@example.com")
        user_id = registered["body"]["id"]
        response = client.post(
            "/api/v1/external-accounts",
            json={"provider": "baidu", "auth_mode": "oauth"},
        )
    assert response.status_code == 403  # provider not allow-listed first

    allowed = settings.model_copy(update={"external_auth_allowed_providers": ["baidu"]})
    service = ExternalAccountService(db_session, allowed)
    with pytest.raises(Exception) as exc_info:
        service.create_or_update(
            user_id,
            provider="baidu",
            auth_mode=ExternalAuthMode.OAUTH,
            secret_reference=None,
            scopes=[],
            expires_at=None,
        )
    assert getattr(exc_info.value, "code", None) == "SECRET_REFERENCE_REQUIRED"
