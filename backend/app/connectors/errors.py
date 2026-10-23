"""Connector-specific exceptions with retryability metadata."""

from __future__ import annotations


class ConnectorError(Exception):
    code = "CONNECTOR_ERROR"

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class ConnectorNotConfigured(ConnectorError):
    code = "CONNECTOR_NOT_CONFIGURED"


class ConnectorAuthError(ConnectorError):
    code = "CONNECTOR_AUTH_ERROR"


class ConnectorHTTPError(ConnectorError):
    code = "CONNECTOR_HTTP_ERROR"

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message, retryable=retryable)
        self.status_code = status_code


class ConnectorParseError(ConnectorError):
    code = "CONNECTOR_PARSE_ERROR"


class UnsafeUrlError(ConnectorError):
    code = "UNSAFE_URL"
