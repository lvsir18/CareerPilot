"""User-initiated import from the Tencent campus recruiting API.

The discovery flow (Tavily + link verification) can never verify Tencent
postings: the campus site renders everything client-side, so a fetched page has
no JD. This service asks Tencent's own public JSON API instead, which returns
the full responsibility/requirements text plus the recruiting project name.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.errors import ConnectorError
from app.connectors.tencent_campus import (
    DEFAULT_PROJECT,
    PROJECTS,
    TencentCampusConnector,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.job import JobSource
from app.services.job_ingestion import upsert_raw_job

MAX_LIMIT = 20


class TencentCampusService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def _source(self) -> JobSource:
        source = self._session.scalar(
            select(JobSource).where(
                JobSource.source_type == "tencent_campus",
                JobSource.source_key == "tencent-campus",
            )
        )
        if source is None:
            source = JobSource(
                source_type="tencent_campus",
                source_key="tencent-campus",
                config_json={},
                enabled=False,  # user-triggered only; never a scheduled crawl
            )
            self._session.add(source)
            self._session.flush()
        return source

    def projects(self) -> list[str]:
        return list(PROJECTS)

    def import_jobs(
        self,
        *,
        keyword: str | None = None,
        project: str = DEFAULT_PROJECT,
        limit: int = 10,
    ) -> dict[str, Any]:
        if project not in PROJECTS:
            raise AppError(
                "INVALID_PROJECT",
                f"不支持的招聘项目：{project}（可选：{'、'.join(PROJECTS)}）",
                status_code=400,
            )
        bounded = max(1, min(limit, MAX_LIMIT))
        connector = TencentCampusConnector(self._settings)
        created = updated = unchanged = 0
        jobs: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        try:
            try:
                # The endpoint ignores projectId, so one wide page is fetched and
                # the recruiting project is filtered locally instead of paging.
                positions = connector.search(keyword, project=project, page_size=100)
            except ConnectorError as exc:
                # Connector exceptions are not ``AppError``, so letting them
                # bubble turns an upstream hiccup into an opaque TOOL_FAILED in
                # the agent run. Surface a readable business error instead.
                raise AppError(
                    "TENCENT_CAMPUS_UNAVAILABLE",
                    f"腾讯校招接口暂不可用：{exc}",
                    status_code=502,
                ) from exc
            source = self._source()
            for row in positions[:bounded]:
                post_id = str(row.get("postId") or "").strip()
                if not post_id:
                    continue
                try:
                    detail = connector.detail(post_id)
                    raw = connector.to_raw_job(detail)
                    outcome = upsert_raw_job(self._session, source, raw)
                except ConnectorError as exc:
                    # A single delisted posting must not abort the whole import.
                    failures.append({"postId": post_id, "reason": str(exc)})
                    continue
                if outcome.created:
                    created += 1
                elif outcome.updated:
                    updated += 1
                else:
                    unchanged += 1
                jobs.append(
                    {
                        "title": raw.title,
                        "city": raw.city,
                        "cities": raw.location_text,
                        "job_type": raw.job_type,
                        "project": raw.recruitment_program,
                        "department": raw.department,
                        "source_url": raw.source_url,
                    }
                )
            self._session.commit()
        finally:
            connector.close()

        return {
            "company": "腾讯",
            "project": project,
            "keyword": keyword or "",
            "matched": len(positions),
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "jobs": jobs,
            "failures": failures,
        }
