from __future__ import annotations

from fakeredis import FakeRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.security.rate_limit import LoginRateLimiter, get_login_rate_limiter
from tests.conftest import AutoCsrfTestClient, _build_app
from tests.factories import register_user

TRUSTED_ORIGIN = "http://localhost:3000"
JSON = {"Content-Type": "application/json"}


def _csrf_token(client: TestClient, cookie_name: str = "careerpilot_csrf") -> str:
    token = client.cookies.get(cookie_name)
    assert token
    return token


def test_login_requires_trusted_origin(plain_client: TestClient) -> None:
    response = plain_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever-123"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_ORIGIN_MISSING"


def test_login_rejects_untrusted_origin(plain_client: TestClient) -> None:
    response = plain_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever-123"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"


def test_register_sets_httponly_session_and_readable_csrf_cookie(
    plain_client: TestClient,
) -> None:
    response = plain_client.post(
        "/api/v1/auth/register",
        json={"email": "cookie@example.com", "password": "strong-pass-123"},
        headers={"Origin": TRUSTED_ORIGIN},
    )

    assert response.status_code == 201
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("careerpilot_session="))
    csrf_cookie = next(c for c in cookies if c.startswith("careerpilot_csrf="))

    assert "httponly" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    assert "secure" not in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert "samesite=lax" in csrf_cookie.lower()


def test_secure_cookie_flag_comes_from_configuration(
    settings: Settings, session_factory: sessionmaker
) -> None:
    secure_settings = settings.model_copy(update={"cookie_secure": True})
    app = _build_app(secure_settings, session_factory)

    with AutoCsrfTestClient(app, secure_settings) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "secure@example.com", "password": "strong-pass-123"},
        )

    cookie = next(
        c for c in response.headers.get_list("set-cookie") if c.startswith("careerpilot_session=")
    )
    assert "secure" in cookie.lower()


def test_csrf_token_required_for_authenticated_writes(plain_client: TestClient) -> None:
    register = plain_client.post(
        "/api/v1/auth/register",
        json={"email": "csrf@example.com", "password": "strong-pass-123"},
        headers={"Origin": TRUSTED_ORIGIN},
    )
    assert register.status_code == 201

    # Safe method works without a token.
    assert plain_client.get("/api/v1/profile/me").status_code == 200

    missing = plain_client.patch(
        "/api/v1/profile/me",
        json={"headline": "缺少 Token"},
        headers={"Origin": TRUSTED_ORIGIN},
    )
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    token = _csrf_token(plain_client)
    wrong = plain_client.patch(
        "/api/v1/profile/me",
        json={"headline": "错误 Token"},
        headers={
            "Origin": TRUSTED_ORIGIN,
            "X-CSRF-Token": "wrong-token",
        },
    )
    assert wrong.status_code == 403

    ok = plain_client.patch(
        "/api/v1/profile/me",
        json={"headline": "正确 Token"},
        headers={"Origin": TRUSTED_ORIGIN, "X-CSRF-Token": token},
    )
    assert ok.status_code == 200


def test_csrf_token_does_not_override_bad_origin(plain_client: TestClient) -> None:
    plain_client.post(
        "/api/v1/auth/register",
        json={"email": "origin@example.com", "password": "strong-pass-123"},
        headers={"Origin": TRUSTED_ORIGIN},
    )
    token = _csrf_token(plain_client)

    response = plain_client.patch(
        "/api/v1/profile/me",
        json={"headline": "bad origin"},
        headers={"Origin": "http://evil.test", "X-CSRF-Token": token},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"


def test_logout_requires_csrf_token(plain_client: TestClient) -> None:
    plain_client.post(
        "/api/v1/auth/register",
        json={"email": "logout-csrf@example.com", "password": "strong-pass-123"},
        headers={"Origin": TRUSTED_ORIGIN},
    )

    blocked = plain_client.post("/api/v1/auth/logout", headers={"Origin": TRUSTED_ORIGIN})
    assert blocked.status_code == 403

    token = _csrf_token(plain_client)
    ok = plain_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": TRUSTED_ORIGIN, "X-CSRF-Token": token},
    )
    assert ok.status_code == 204
    assert plain_client.get("/api/v1/auth/me").status_code == 401


def test_csrf_endpoint_issues_rotating_token(plain_client: TestClient) -> None:
    first = plain_client.get("/api/v1/auth/csrf")
    second = plain_client.get("/api/v1/auth/csrf")

    assert first.status_code == 200
    assert first.json()["data"]["csrf_token"]
    assert first.json()["data"]["header_name"] == "X-CSRF-Token"
    assert first.json()["data"]["csrf_token"] != second.json()["data"]["csrf_token"]


def test_login_rotates_session_and_csrf_tokens(client: TestClient) -> None:
    register_user(client, email="rotate@example.com", password="strong-pass-123")
    first_session = client.cookies.get("careerpilot_session")
    first_csrf = client.cookies.get("careerpilot_csrf")

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "rotate@example.com", "password": "strong-pass-123"},
    )

    assert login.status_code == 200
    assert client.cookies.get("careerpilot_session") != first_session
    assert client.cookies.get("careerpilot_csrf") != first_csrf


def _rate_limited_client(
    app: FastAPI,
    settings: Settings,
    *,
    ip_attempts: int = 3,
    account_attempts: int = 3,
) -> tuple[AutoCsrfTestClient, LoginRateLimiter]:
    limiter = LoginRateLimiter(
        FakeRedis(decode_responses=True),
        enabled=True,
        ip_attempts=ip_attempts,
        ip_window_seconds=60,
        account_attempts=account_attempts,
        account_window_seconds=60,
    )
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    return AutoCsrfTestClient(app, settings), limiter


def test_login_rate_limit_returns_429(app: FastAPI, settings: Settings, db_session) -> None:
    client, _ = _rate_limited_client(app, settings)
    register_user(client, email="limited@example.com", password="strong-pass-123")
    client.post("/api/v1/auth/logout")

    with client:
        for _ in range(3):
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "limited@example.com", "password": "wrong-password"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": "limited@example.com", "password": "wrong-password"},
        )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.json()["error"]["details"]["retry_after_seconds"] > 0


def test_rate_limit_counts_account_across_ips(app: FastAPI, settings: Settings, db_session) -> None:
    client, _ = _rate_limited_client(app, settings)
    register_user(client, email="account-limit@example.com", password="strong-pass-123")

    with client:
        for index in range(3):
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "account-limit@example.com", "password": "wrong-password"},
                headers={"X-Forwarded-For": f"10.0.0.{index + 1}"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": "account-limit@example.com", "password": "wrong-password"},
            headers={"X-Forwarded-For": "10.0.0.9"},
        )

    assert blocked.status_code == 429


def test_rate_limit_counts_ip_across_accounts(app: FastAPI, settings: Settings, db_session) -> None:
    client, _ = _rate_limited_client(app, settings)

    with client:
        for index in range(3):
            response = client.post(
                "/api/v1/auth/login",
                json={"email": f"ip-{index}@example.com", "password": "wrong-password"},
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": "another@example.com", "password": "wrong-password"},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )

    assert blocked.status_code == 429


class _BrokenRedis:
    def pipeline(self):
        raise ConnectionError("redis down")


def test_rate_limiter_fails_open_when_redis_is_down(app: FastAPI, settings: Settings) -> None:
    broken = LoginRateLimiter(
        _BrokenRedis(),  # type: ignore[arg-type]
        enabled=True,
        ip_attempts=1,
        ip_window_seconds=60,
        account_attempts=1,
        account_window_seconds=60,
    )
    app.dependency_overrides[get_login_rate_limiter] = lambda: broken
    client = AutoCsrfTestClient(app, settings)
    register_user(client, email="fail-open@example.com", password="strong-pass-123")

    with client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "fail-open@example.com", "password": "strong-pass-123"},
        )

    assert response.status_code == 200


def test_successful_login_resets_account_counter(
    app: FastAPI, settings: Settings, db_session
) -> None:
    client, _limiter = _rate_limited_client(app, settings, ip_attempts=20, account_attempts=4)
    register_user(client, email="reset@example.com", password="strong-pass-123")

    with client:
        for _ in range(3):
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={"email": "reset@example.com", "password": "wrong-password"},
                ).status_code
                == 401
            )
        success = client.post(
            "/api/v1/auth/login",
            json={"email": "reset@example.com", "password": "strong-pass-123"},
        )
        assert success.status_code == 200

        # Counter was reset, so another failure is not immediately throttled.
        again = client.post(
            "/api/v1/auth/login",
            json={"email": "reset@example.com", "password": "wrong-password"},
        )
        assert again.status_code in {401, 429}
