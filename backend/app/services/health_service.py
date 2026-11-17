"""Health and readiness domain service.

The API layer only maps this report to HTTP; connection handling lives in the
infrastructure modules so that checks stay injectable in tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class ReadinessReport:
    checks: list[CheckResult] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def ready(self) -> bool:
        return all(check.ok for check in self.checks)


class HealthService:
    """Aggregates dependency checks (database, cache)."""

    def __init__(
        self,
        database_check: Callable[[], bool],
        cache_check: Callable[[], bool],
    ) -> None:
        self._database_check = database_check
        self._cache_check = cache_check

    def _run(self, name: str, check: Callable[[], bool]) -> CheckResult:
        try:
            ok = bool(check())
        except Exception as exc:  # defensive: checks should not raise
            return CheckResult(name=name, ok=False, detail=type(exc).__name__)
        return CheckResult(name=name, ok=ok, detail=None if ok else "unreachable")

    def readiness(self) -> ReadinessReport:
        return ReadinessReport(
            checks=[
                self._run("database", self._database_check),
                self._run("redis", self._cache_check),
            ]
        )
