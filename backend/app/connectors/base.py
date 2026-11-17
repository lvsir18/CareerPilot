"""Connector protocol.

Connectors only fetch and parse source data; normalization, validation,
deduplication and persistence are handled by :mod:`app.services.job_sync`.
"""

from __future__ import annotations

from typing import Any, ClassVar, Protocol

from app.connectors.schemas import ConnectorHealth, RawJob


class JobConnector(Protocol):
    source_type: ClassVar[str]

    def fetch_jobs(self, source_config: dict[str, Any]) -> list[RawJob]:
        """Fetch all visible jobs (bounded by configured pagination limits)."""
        ...

    def fetch_job_detail(self, source_job_id: str, source_config: dict[str, Any]) -> RawJob | None:
        """Optional single-job fetch; return None when the list already has JD."""
        ...

    def health_check(self, source_config: dict[str, Any]) -> ConnectorHealth:
        """Report configuration and reachability without mutating data."""
        ...
