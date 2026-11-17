"""Structured JSON logging with request correlation.

Logs are written to stdout as one JSON object per line so that Docker / any log
collector can consume them without a paid tracing backend. Resume text, tokens
and cookies must never be logged by callers.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)

_STANDARD_LOG_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

_RESERVED_FIELDS = frozenset({"timestamp", "level", "logger", "message", "request_id", "run_id"})


class JsonFormatter(logging.Formatter):
    """Serialise log records into a single-line JSON payload."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
            "run_id": getattr(record, "run_id", None) or run_id_var.get(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS or key in _RESERVED_FIELDS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that injects request/run correlation ids."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = dict(kwargs.get("extra") or {})
        extra.setdefault("request_id", request_id_var.get())
        run_id = run_id_var.get()
        if run_id is not None:
            extra.setdefault("run_id", run_id)
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(level: str = "INFO") -> None:
    """Install a single stdout JSON handler on the root logger."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Uvicorn ships its own handlers; route everything through the JSON handler
    # instead and log access events ourselves with duration and request id.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []
    uvicorn_access.propagate = False


def get_logger(name: str) -> ContextLogger:
    """Return a logger that always carries request/run correlation ids."""
    return ContextLogger(logging.getLogger(name), {})
