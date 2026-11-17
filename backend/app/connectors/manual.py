"""Manual/authorized JSON import connector.

The deployment admin exports jobs from an official source they are allowed to
use and places the file under ``MANUAL_IMPORT_DIR``. This connector never
fetches arbitrary URLs and never marks records as demo.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.connectors.errors import ConnectorNotConfigured, ConnectorParseError
from app.connectors.schemas import ConnectorHealth, RawJob
from app.core.config import Settings
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus


class ManualJsonConnector:
    source_type = "manual"

    def __init__(self, settings: Settings) -> None:
        self._base_dir = Path(settings.manual_import_dir).expanduser().resolve()

    def _path(self, source_config: dict[str, Any]) -> Path:
        filename = str(source_config.get("filename") or "").strip()
        if not filename:
            raise ConnectorNotConfigured("manual 数据源缺少 config.filename")
        if Path(filename).name != filename:
            raise ConnectorParseError("filename 不允许包含路径分隔符")
        path = (self._base_dir / filename).resolve()
        if self._base_dir not in path.parents and path != self._base_dir:
            raise ConnectorParseError("导入文件路径越界")
        if not path.is_file():
            raise ConnectorNotConfigured(f"导入文件不存在: {filename}")
        return path

    def fetch_jobs(self, source_config: dict[str, Any]) -> list[RawJob]:
        path = self._path(source_config)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConnectorParseError("手工导入文件不是合法 JSON") from exc

        items = payload.get("jobs", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ConnectorParseError("手工导入文件缺少 jobs 数组")

        source_key = str(source_config.get("source_key") or "manual-import")
        jobs: list[RawJob] = []
        for item in items:
            if not isinstance(item, dict):
                raise ConnectorParseError("jobs 数组元素必须是对象")
            published_at = None
            if item.get("published_at"):
                published_at = datetime.fromisoformat(
                    str(item["published_at"]).replace("Z", "+00:00")
                )
            jobs.append(
                RawJob(
                    source_type=self.source_type,
                    source_key=source_key,
                    source_job_id=str(item["source_job_id"]),
                    company=str(item["company"]),
                    title=str(item["title"]),
                    source_url=str(item["source_url"]),
                    description=item.get("description"),
                    department=item.get("department"),
                    location_text=item.get("location_text"),
                    city=item.get("city"),
                    job_type=item.get("job_type"),
                    recruitment_program=item.get("recruitment_program"),
                    requirements=list(item.get("requirements") or []),
                    published_at=published_at,
                    raw_payload=item,
                    is_demo=False,
                    status=JobStatus(str(item.get("status", "unknown"))),
                    source_method=JobSourceMethod.MANUAL_IMPORT,
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
        try:
            count = len(self.fetch_jobs(source_config))
        except ConnectorNotConfigured as exc:
            return ConnectorHealth(configured=False, ok=False, message=exc.message)
        except ConnectorParseError as exc:
            return ConnectorHealth(configured=True, ok=False, message=exc.message)
        return ConnectorHealth(
            configured=True,
            ok=True,
            message=f"手工导入文件可用，共 {count} 条（is_demo=false）",
        )


# Explicit architecture name; behavior is the authorized JSON import above.
ManualImportConnector = ManualJsonConnector
