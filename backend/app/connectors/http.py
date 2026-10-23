"""Hardened HTTP client for external job sources.

Security properties:
- HTTPS/HTTP only, no userinfo, allow-listed hosts only.
- DNS resolution rejects loopback/private/link-local/reserved/multicast targets.
- Redirects are followed manually, each hop re-validated (max 3).
- Request timeout, bounded retries for 429/5xx/network errors, response size cap.
- Per-client minimum request interval (source-level throttling).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.connectors.errors import (
    ConnectorHTTPError,
    ConnectorParseError,
    UnsafeUrlError,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
REDIRECT_STATUS = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 3
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class SafeHttpClient:
    def __init__(
        self,
        *,
        allowed_hosts: set[str],
        user_agent: str,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
        min_interval_seconds: float = 1.0,
        max_response_bytes: int = 5_000_000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._allowed_hosts = {host.lower() for host in allowed_hosts}
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._min_interval = min_interval_seconds
        self._max_response_bytes = max_response_bytes
        self._last_request_at = 0.0
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain;q=0.9, */*;q=0.5",
            },
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SafeHttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _validate_url(self, url: str) -> str:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise UnsafeUrlError("URL 无法解析") from exc

        if parsed.scheme not in {"http", "https"}:
            raise UnsafeUrlError("仅允许 http/https URL")
        if parsed.username or parsed.password:
            raise UnsafeUrlError("URL 不允许包含用户凭据")
        if not parsed.hostname:
            raise UnsafeUrlError("URL 缺少主机名")

        host = parsed.hostname.lower()
        if host not in self._allowed_hosts:
            raise UnsafeUrlError(f"域名不在白名单内: {host}")
        if parsed.port not in {None, 80, 443}:
            raise UnsafeUrlError("不允许非常规端口")

        try:
            addresses = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UnsafeUrlError(f"域名无法解析: {host}") from exc

        for entry in addresses:
            ip = ipaddress.ip_address(entry[4][0])
            if (
                not ip.is_global
                or ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
                or (isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT)
            ):
                raise UnsafeUrlError(f"域名解析到非公网地址: {host}")
        return url

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if self._min_interval > 0 and elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _request_once(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        current = self._validate_url(url)
        for _ in range(MAX_REDIRECTS + 1):
            self._throttle()
            try:
                response = self._client.request(method, current, **kwargs)
            except httpx.TimeoutException as exc:
                raise ConnectorHTTPError("外部请求超时", retryable=True) from exc
            except httpx.TransportError as exc:
                raise ConnectorHTTPError("外部网络请求失败", retryable=True) from exc

            if response.status_code in REDIRECT_STATUS:
                location = response.headers.get("location")
                if not location:
                    raise ConnectorHTTPError("重定向缺少 Location", retryable=False)
                current = self._validate_url(urljoin(current, location))
                continue

            content_length = response.headers.get("content-length")
            try:
                too_large = bool(content_length) and int(content_length) > self._max_response_bytes
            except ValueError:
                too_large = False
            if too_large:
                raise ConnectorHTTPError("响应体超过大小限制", retryable=False)

            body = response.content
            if len(body) > self._max_response_bytes:
                raise ConnectorHTTPError("响应体超过大小限制", retryable=False)

            if response.status_code >= 400:
                raise ConnectorHTTPError(
                    f"外部服务返回 HTTP {response.status_code}",
                    status_code=response.status_code,
                    retryable=response.status_code in RETRYABLE_STATUS,
                )
            return response
        raise ConnectorHTTPError("重定向次数超过限制", retryable=False)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: ConnectorHTTPError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._request_once(method, url, **kwargs)
            except ConnectorHTTPError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self._max_retries:
                    raise
                delay = self._backoff * (2**attempt)
                logger.warning(
                    "connector_request_retry",
                    extra={
                        "attempt": attempt + 1,
                        "status_code": exc.status_code,
                        "delay_seconds": delay,
                    },
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        response = self.request("POST", url, data=data)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorParseError("来源返回的不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise ConnectorParseError("来源 JSON 顶层结构异常")
        return payload

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.request("POST", url, json=payload)
        try:
            body = response.json()
        except ValueError as exc:
            raise ConnectorParseError("来源返回的不是合法 JSON") from exc
        if not isinstance(body, dict):
            raise ConnectorParseError("来源 JSON 顶层结构异常")
        return body

    def get_json(self, url: str) -> dict[str, Any]:
        response = self.request("GET", url)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorParseError("来源返回的不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise ConnectorParseError("来源 JSON 顶层结构异常")
        return payload

    def get_text(self, url: str) -> str:
        response = self.request("GET", url)
        return response.content.decode(response.encoding or "utf-8", errors="replace")
