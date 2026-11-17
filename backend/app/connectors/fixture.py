"""Offline demo fixture connector (is_demo=true, never production data)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.connectors.errors import ConnectorParseError
from app.connectors.schemas import ConnectorHealth, RawJob
from app.core.config import Settings
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "demo_jobs.json"


class FixtureConnector:
    source_type = "fixture"

    def __init__(self, settings: Settings, path: Path | None = None) -> None:
        self._path = path or FIXTURE_PATH
        self._demo_mode = settings.demo_mode

    def _payload(self) -> dict[str, Any]:
        if not self._path.exists():
            raise ConnectorParseError(f"演示数据文件不存在: {self._path.name}")
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConnectorParseError("演示数据不是合法 JSON") from exc

    def fetch_jobs(self, source_config: dict[str, Any]) -> list[RawJob]:
        payload = self._payload()
        source = payload.get("source", {})
        source_key = source_config.get("source_key") or source.get("source_key", "careerpilot-demo")
        jobs: list[RawJob] = []
        for item in payload.get("jobs", []):
            published_at = None
            if item.get("published_at"):
                published_at = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            jobs.append(
                RawJob(
                    source_type=self.source_type,
                    source_key=source_key,
                    source_job_id=item["source_job_id"],
                    company=item["company"],
                    title=item["title"],
                    source_url=item["source_url"],
                    description=item.get("description"),
                    department=item.get("department"),
                    location_text=item.get("location_text"),
                    city=item.get("city"),
                    job_type=item.get("job_type"),
                    recruitment_program=item.get("recruitment_program"),
                    requirements=list(item.get("requirements") or []),
                    published_at=published_at,
                    raw_payload=item,
                    is_demo=True,
                    status=JobStatus(item.get("status", "unknown")),
                    source_method=JobSourceMethod.FIXTURE,
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )
        return jobs

    def fetch_job_detail(self, source_job_id: str, source_config: dict[str, Any]) -> RawJob | None:
        return next(
            (job for job in self.fetch_jobs(source_config) if job.source_job_id == source_job_id),
            None,
        )

    def health_check(self, source_config: dict[str, Any]) -> ConnectorHealth:
        if not self._demo_mode:
            return ConnectorHealth(
                configured=True,
                ok=False,
                message="DEMO_MODE=false 时演示连接器不可用",
            )
        try:
            count = len(self.fetch_jobs(source_config))
        except ConnectorParseError as exc:
            return ConnectorHealth(configured=True, ok=False, message=exc.message)
        return ConnectorHealth(
            configured=True,
            ok=True,
            message=f"演示数据源可用，共 {count} 条（全部 is_demo=true）",
        )
