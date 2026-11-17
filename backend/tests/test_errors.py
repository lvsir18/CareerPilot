from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["message"] == "资源不存在"
    assert error["details"] == {}


def test_validation_errors_use_error_envelope(app: FastAPI) -> None:
    @app.get("/_test/validation")
    def _validation(limit: int = 1) -> dict[str, int]:
        return {"limit": limit}

    with TestClient(app) as client:
        response = client.get("/_test/validation", params={"limit": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"] == ["query", "limit"]


def test_app_error_keeps_code_and_details(app: FastAPI) -> None:
    @app.get("/_test/app-error")
    def _app_error() -> None:
        raise AppError(
            code="PROFILE_NOT_READY",
            message="画像尚未确认",
            status_code=409,
            details={"profile_version": None},
        )

    with TestClient(app) as client:
        response = client.get("/_test/app-error")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "PROFILE_NOT_READY",
        "message": "画像尚未确认",
        "details": {"profile_version": None},
    }


def test_unhandled_exception_hides_internals(app: FastAPI) -> None:
    @app.get("/_test/boom")
    def _boom() -> None:
        raise RuntimeError("database password is hunter2")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test/boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
