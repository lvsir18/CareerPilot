"""Unified API error contract.

Every error response has the shape::

    {"error": {"code": "NOT_FOUND", "message": "...", "details": {}}}

HTTP status codes follow the specification: 401/403/404/409/422/429/503.
Internal exception details (SQL, credentials, stack traces) are never exposed.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_MESSAGES: dict[int, str] = {
    400: "请求参数错误",
    401: "未登录或登录已过期",
    403: "无权访问该资源",
    404: "资源不存在",
    405: "请求方法不被允许",
    409: "资源冲突",
    429: "请求过于频繁",
    500: "服务器内部错误",
    503: "服务暂时不可用",
}

_STATUS_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    """Expected business error raised by services.

    Services raise this; the handler renders the shared error envelope.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers or {}


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _default_code(status_code: int) -> str:
    return _STATUS_CODE_MAP.get(status_code, "HTTP_ERROR")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Drop documentation URLs; clients only need loc/msg/type.
        errors = [
            {key: value for key, value in error.items() if key != "url"} for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "VALIDATION_ERROR",
                "请求参数校验失败",
                {"errors": jsonable_encoder(errors)},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, str):
            # Replace framework defaults ("Not Found") with product copy but
            # keep explicit, domain-specific messages raised by services.
            is_framework_default = exc.detail == HTTPStatus(exc.status_code).phrase
            message = (
                _DEFAULT_MESSAGES.get(exc.status_code, exc.detail)
                if is_framework_default
                else exc.detail
            )
        else:
            message = _DEFAULT_MESSAGES.get(exc.status_code, HTTPStatus(exc.status_code).phrase)
        details = {} if isinstance(exc.detail, str) else {"detail": exc.detail}
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(_default_code(exc.status_code), message, details),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_type": type(exc).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content=error_payload("INTERNAL_ERROR", "服务器内部错误，请稍后重试"),
        )
