from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_health_service
from app.core.middleware import REQUEST_ID_HEADER
from app.services.health_service import HealthService


def test_healthz_reports_process_status_without_dependencies(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["demo_mode"] is True


def test_request_id_header_is_generated(client: TestClient) -> None:
    response = client.get("/healthz")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 32


def test_request_id_header_is_propagated_when_safe(client: TestClient) -> None:
    response = client.get("/healthz", headers={REQUEST_ID_HEADER: "trace-123"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-123"


def test_request_id_header_rejects_unsafe_values(client: TestClient) -> None:
    response = client.get("/healthz", headers={REQUEST_ID_HEADER: "bad value!"})

    assert response.headers[REQUEST_ID_HEADER] != "bad value!"


def test_readyz_ok_when_all_dependencies_are_healthy(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_health_service] = lambda: HealthService(
        database_check=lambda: True,
        cache_check=lambda: True,
    )

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert [check["name"] for check in body["checks"]] == ["database", "redis"]
    assert all(check["status"] == "ok" for check in body["checks"])


def test_readyz_returns_503_with_error_contract(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_health_service] = lambda: HealthService(
        database_check=lambda: True,
        cache_check=lambda: False,
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert body["error"]["details"]["checks"][1] == {
        "name": "redis",
        "status": "error",
        "detail": "unreachable",
    }


def test_health_service_never_raises_when_a_check_breaks() -> None:
    def broken() -> bool:
        raise ConnectionError("boom")

    report = HealthService(database_check=broken, cache_check=lambda: True).readiness()

    assert report.ready is False
    assert report.checks[0].detail == "ConnectionError"
