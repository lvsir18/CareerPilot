"""Uniform connector contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus


@dataclass(slots=True)
class RawJob:
    """Normalized shape every connector must produce.

    Missing source fields stay ``None`` — connectors must never invent publish
    dates, salaries, cities or status.
    """

    source_type: str
    source_key: str
    source_job_id: str
    company: str
    title: str
    source_url: str
    description: str | None = None
    department: str | None = None
    location_text: str | None = None
    city: str | None = None
    job_type: str | None = None
    recruitment_program: str | None = None
    requirements: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    raw_payload: dict[str, Any] = field(default_factory=dict)
    is_demo: bool = False
    status: JobStatus = JobStatus.UNKNOWN
    source_method: JobSourceMethod = JobSourceMethod.UNKNOWN
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verified_at: datetime | None = None


@dataclass(frozen=True)
class ConnectorHealth:
    configured: bool
    ok: bool
    message: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
