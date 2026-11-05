from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.user import User, UserSession
from tests.factories import register_user


def test_register_creates_user_and_session_cookie(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "Alice@Example.com", "password": "strong-pass-123"},
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["email"] == "alice@example.com"
    assert "password" not in body

    cookie = response.headers["set-cookie"].lower()
    assert "careerpilot_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "alice@example.com"


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    register_user(client, email="dup@example.com")

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "DUP@example.com", "password": "strong-pass-123"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_weak_or_invalid_payload_is_rejected(client: TestClient) -> None:
    weak = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short"},
    )
    assert weak.status_code == 422

    invalid_email = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "strong-pass-123"},
    )
    assert invalid_email.status_code == 422


def test_password_is_hashed_in_database(client: TestClient, db_session: Session) -> None:
    register_user(client, email="hash@example.com", password="strong-pass-123")

    user = db_session.scalar(select(User).where(User.email == "hash@example.com"))

    assert user is not None
    assert user.password_hash != "strong-pass-123"
    assert user.password_hash.startswith("$argon2")


def test_login_logout_flow(client: TestClient) -> None:
    register_user(client, email="flow@example.com", password="strong-pass-123")
    client.post("/api/v1/auth/logout")

    assert client.get("/api/v1/auth/me").status_code == 401

    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "Flow@Example.com", "password": "strong-pass-123"},
    )
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_revoked_session_cannot_be_reused(client: TestClient) -> None:
    register_user(client, email="revoke@example.com")
    cookie = client.cookies.get("careerpilot_session")
    assert cookie

    client.post("/api/v1/auth/logout")
    client.cookies.set("careerpilot_session", cookie)

    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(client: TestClient, db_session: Session) -> None:
    register_user(client, email="expired@example.com")

    db_session.execute(
        update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db_session.commit()

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_change_password_keeps_current_session_and_rotates_credentials(
    client: TestClient,
) -> None:
    register_user(client, email="change@example.com", password="old-pass-123")

    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": "old-pass-123", "new_password": "new-pass-456"},
    )

    assert response.status_code == 204
    # Changing the password must not log the current tab out.
    assert client.get("/api/v1/auth/me").status_code == 200

    client.post("/api/v1/auth/logout")
    old = client.post(
        "/api/v1/auth/login",
        json={"email": "change@example.com", "password": "old-pass-123"},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login",
        json={"email": "change@example.com", "password": "new-pass-456"},
    )
    assert new.status_code == 200


def test_change_password_requires_the_current_password(client: TestClient) -> None:
    register_user(client, email="wrong-current@example.com", password="old-pass-123")

    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-the-password", "new_password": "new-pass-456"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_password_reset_is_disabled_by_default(client: TestClient) -> None:
    register_user(client, email="reset-off@example.com", password="old-pass-123")

    response = client.post(
        "/api/v1/auth/password/reset",
        json={"email": "reset-off@example.com", "new_password": "new-pass-456"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PASSWORD_RESET_DISABLED"


def test_password_reset_works_when_enabled(client: TestClient, settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "password_reset_enabled", True)
    register_user(client, email="reset-on@example.com", password="old-pass-123")
    client.post("/api/v1/auth/logout")

    response = client.post(
        "/api/v1/auth/password/reset",
        json={"email": "reset-on@example.com", "new_password": "new-pass-456"},
    )

    assert response.status_code == 204
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "reset-on@example.com", "password": "new-pass-456"},
    )
    assert login.status_code == 200


def test_protected_endpoints_require_login(client: TestClient) -> None:
    for path in (
        "/api/v1/auth/me",
        "/api/v1/profile/me",
        "/api/v1/jobs",
        "/api/v1/saved-jobs",
        "/api/v1/applications",
    ):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "AUTH_REQUIRED"
