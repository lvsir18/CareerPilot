from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.connectors.alibaba import AlibabaTopConnector
from app.connectors.errors import (
    ConnectorHTTPError,
    ConnectorNotConfigured,
    ConnectorParseError,
    UnsafeUrlError,
)
from app.connectors.fixture import FixtureConnector
from app.connectors.http import SafeHttpClient
from app.connectors.manual import ManualJsonConnector
from app.core.config import Settings
from app.db.models.enums import JobStatus

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_fixture_connector_marks_all_records_as_demo() -> None:
    connector = FixtureConnector(Settings(app_env="test", demo_mode=True))

    jobs = connector.fetch_jobs({})

    assert len(jobs) == 8
    assert all(job.is_demo for job in jobs)
    assert all(job.source_type == "fixture" for job in jobs)
    assert sum(job.published_at is None for job in jobs) == 1
    assert any(job.status == JobStatus.CLOSED for job in jobs)
    assert connector.health_check({}).ok is True


def test_fixture_connector_disabled_without_demo_mode() -> None:
    connector = FixtureConnector(Settings(app_env="test", demo_mode=False))

    health = connector.health_check({})

    assert health.ok is False
    assert "DEMO_MODE" in health.message


def test_manual_connector_reads_authorized_file(tmp_path: Path) -> None:
    payload = {
        "jobs": [
            {
                "source_job_id": "manual-1",
                "company": "示例公司",
                "title": "Agent 工程师",
                "source_url": "https://careers.example.com/jobs/manual-1",
                "description": "真实来源导入",
                "city": "北京",
                "job_type": "校招",
                "status": "open",
                "published_at": "2026-10-01T00:00:00Z",
            }
        ]
    }
    (tmp_path / "jobs.json").write_text(json.dumps(payload), encoding="utf-8")
    settings = Settings(app_env="test", manual_import_dir=tmp_path)

    jobs = ManualJsonConnector(settings).fetch_jobs({"filename": "jobs.json"})

    assert len(jobs) == 1
    assert jobs[0].is_demo is False
    assert jobs[0].job_type == "校招"
    assert jobs[0].published_at == datetime(2026, 10, 1, tzinfo=UTC)


def test_manual_connector_rejects_path_traversal(tmp_path: Path) -> None:
    settings = Settings(app_env="test", manual_import_dir=tmp_path)

    with pytest.raises(ConnectorParseError):
        ManualJsonConnector(settings).fetch_jobs({"filename": "../secret.json"})


def test_manual_connector_reports_missing_file(tmp_path: Path) -> None:
    settings = Settings(app_env="test", manual_import_dir=tmp_path)

    health = ManualJsonConnector(settings).health_check({"filename": "missing.json"})

    assert health.configured is False
    assert health.ok is False


def _alibaba_settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "alibaba_app_key": "test-key",
        "alibaba_app_secret": "test-secret",
        "alibaba_tenant_id": "10000000000",
        "alibaba_position_url_template": "https://talent.alibaba.com/off-campus/position-detail?positionId={position_id}",
    }
    values.update(overrides)
    return Settings(**values)


class _FakeAlibabaClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def post_form(self, url: str, data: dict[str, str]) -> dict:
        self.calls.append({"url": url, "data": data})
        return self.payload


def test_alibaba_connector_parses_recorded_response() -> None:
    payload = json.loads((FIXTURE_DIR / "alibaba_pagesearch.json").read_text(encoding="utf-8"))
    fake = _FakeAlibabaClient(payload)
    connector = AlibabaTopConnector(_alibaba_settings(), client=fake)  # type: ignore[arg-type]

    jobs = connector.fetch_jobs({"source_key": "alibaba-careers"})

    assert len(jobs) == 2
    first = jobs[0]
    assert first.source_job_id == "9000000001"
    assert first.title == "大模型算法工程师（测试夹具）"
    assert first.city == "杭州"
    assert first.department == "测试事业群"
    assert first.published_at is None
    assert first.status == JobStatus.UNKNOWN
    assert first.is_demo is False
    assert first.source_url.endswith("positionId=9000000001")
    assert "熟悉 PyTorch" in first.requirements

    sent = fake.calls[0]["data"]
    assert sent["method"] == "alibaba.recruit.position.pagesearch"
    assert sent["sign"]
    assert "param_official_position_page_query_param" in sent


def test_alibaba_connector_requires_configuration() -> None:
    connector = AlibabaTopConnector(Settings(app_env="test"), client=_FakeAlibabaClient({}))  # type: ignore[arg-type]

    health = connector.health_check({})

    assert health.configured is False
    with pytest.raises(ConnectorNotConfigured):
        connector.fetch_jobs({})


def test_alibaba_connector_surfaces_api_error() -> None:
    connector = AlibabaTopConnector(
        _alibaba_settings(),
        client=_FakeAlibabaClient(
            {"error_response": {"msg": "Remote service error", "sub_msg": "非法参数"}}
        ),  # type: ignore[arg-type]
    )

    with pytest.raises(ConnectorParseError):
        connector.fetch_jobs({})


def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "localhost":
            address = "127.0.0.1"
        else:
            try:
                address = str(__import__("ipaddress").ip_address(host))
            except ValueError:
                address = "93.184.216.34"
        return [(2, 1, 6, "", (address, port or 443))]

    monkeypatch.setattr("app.connectors.http.socket.getaddrinfo", fake_getaddrinfo)


def test_safe_http_rejects_private_and_unlisted_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_dns(monkeypatch)
    client = SafeHttpClient(
        allowed_hosts={"example.com", "localhost"},
        user_agent="test",
        min_interval_seconds=0,
    )

    with pytest.raises(UnsafeUrlError):
        client._validate_url("http://127.0.0.1/jobs")
    with pytest.raises(UnsafeUrlError):
        client._validate_url("http://localhost/jobs")
    with pytest.raises(UnsafeUrlError):
        client._validate_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(UnsafeUrlError):
        client._validate_url("https://evil.example.net/jobs")
    with pytest.raises(UnsafeUrlError):
        client._validate_url("ftp://example.com/jobs")
    client.close()


def test_safe_http_blocks_redirect_to_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "http://127.0.0.1/internal"}, request=request
        )

    client = SafeHttpClient(
        allowed_hosts={"example.com"},
        user_agent="test",
        min_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(UnsafeUrlError):
        client.get_json("https://example.com/jobs")
    client.close()


def test_safe_http_retries_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_dns(monkeypatch)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = SafeHttpClient(
        allowed_hosts={"example.com"},
        user_agent="test",
        max_retries=1,
        backoff_seconds=0,
        min_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    assert client.get_json("https://example.com/jobs") == {"ok": True}
    assert calls["count"] == 2
    client.close()


def test_safe_http_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "9999999"},
            content=b"{}",
            request=request,
        )

    client = SafeHttpClient(
        allowed_hosts={"example.com"},
        user_agent="test",
        max_response_bytes=1000,
        min_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ConnectorHTTPError):
        client.get_json("https://example.com/jobs")
    client.close()


def test_safe_http_rechecks_dns_resolution_on_each_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    addresses = iter(["93.184.216.34", "127.0.0.1"])

    def rebinding_dns(host, port, *args, **kwargs):
        return [(2, 1, 6, "", (next(addresses), port or 443))]

    monkeypatch.setattr("app.connectors.http.socket.getaddrinfo", rebinding_dns)
    client = SafeHttpClient(
        allowed_hosts={"example.com"},
        user_agent="test",
        min_interval_seconds=0,
    )

    assert client._validate_url("https://example.com/jobs") == "https://example.com/jobs"
    with pytest.raises(UnsafeUrlError):
        # A second resolution cannot silently switch to loopback.
        client._validate_url("https://example.com/jobs")
    client.close()
