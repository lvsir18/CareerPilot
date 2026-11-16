"""Official-source job search (API route + browser-rendered route).

The discovery flow (Tavily + HTML verification) structurally cannot verify jobs
on SPA career sites: the fetched HTML carries no job data, so those companies
only ever produced unverifiable "candidate links". This service goes to the
source instead:

- ``api``      → Tencent publishes plain JSON (no signature).
- ``rendered`` → ByteDance/Xiaohongshu/Bilibili/Meituan sign their XHRs in the
  browser, so we load the official public search page with a headless browser
  and read the JSON it receives.

Fetching runs in a small thread pool (the DB session stays on the main thread),
and results are cached briefly per (company, keyword) so repeated searches do
not re-render the same page.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.errors import ConnectorError
from app.connectors.jd_campus import JdCampusConnector
from app.connectors.official_sources import (
    API_SOURCES,
    COMPANY_LABELS,
    RENDERED_SOURCES,
    UNSUPPORTED_NOTES,
    official_catalog,
    official_company_keys,
)
from app.connectors.rendered import RenderedJobSearch
from app.connectors.schemas import RawJob
from app.connectors.tencent_campus import TencentCampusConnector
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.job import JobSource
from app.services.job_ingestion import upsert_raw_job

# Per-company ceiling for one crawl. The maintenance "discover" depth selects
# 10/30/50; capping at 10 silently made the deeper modes identical to 快速.
MAX_LIMIT = 100
CACHE_TTL_SECONDS = 600

_cache: dict[tuple[str, str], tuple[float, list[RawJob]]] = {}
_cache_lock = threading.Lock()


@dataclass
class _Fetched:
    key: str
    jobs: list[RawJob]
    error: str | None = None


def supported_sources() -> list[dict[str, Any]]:
    """Full company catalog: ``supported`` tells the UI what is clickable."""
    return official_catalog()


class OfficialJobsService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    # ---------------------------------------------------------------- catalog
    def supported(self) -> list[dict[str, Any]]:
        return supported_sources()

    # ----------------------------------------------------------------- search
    def search(
        self,
        *,
        companies: list[str],
        keyword: str | None = None,
        limit: int = MAX_LIMIT,
        project: str | None = None,
    ) -> dict[str, Any]:
        requested = [key for key in dict.fromkeys(companies) if key]
        if not requested:
            requested = ["tencent"]
        unknown = [key for key in requested if key not in COMPANY_LABELS]
        if unknown:
            raise AppError(
                "UNSUPPORTED_COMPANY",
                f"未知企业：{'、'.join(unknown)}",
                status_code=400,
            )
        # Multi-select must not fail as a batch just because one company is not
        # wired yet: skip it and report the reason in this run's summary.
        unsupported = [key for key in requested if key not in official_company_keys()]
        requested = [key for key in requested if key in official_company_keys()]
        if not requested:
            raise AppError(
                "UNSUPPORTED_COMPANY",
                "所选企业暂不支持官方直连，请改用上方筛选搜索或「导入岗位」手动添加",
                status_code=400,
            )
        bounded = max(1, min(limit, MAX_LIMIT))
        workers = min(4, len(requested))

        results: list[_Fetched] = []
        if workers <= 1:
            results = [self._fetch(key, keyword, bounded, project) for key in requested]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(self._fetch, key, keyword, bounded, project) for key in requested
                ]
                for future in futures:
                    try:
                        results.append(future.result())
                    except Exception as exc:  # defensive: never fail the batch
                        results.append(_Fetched(key="unknown", jobs=[], error=str(exc)))

        results.extend(
            _Fetched(
                key=key,
                jobs=[],
                error=f"暂不支持官方直连：{UNSUPPORTED_NOTES.get(key, '未适配')}",
            )
            for key in unsupported
        )

        order = {key: idx for idx, key in enumerate([*requested, *unsupported])}
        results.sort(key=lambda item: order.get(item.key, 99))

        created = updated = unchanged = 0
        summary: list[dict[str, Any]] = []
        jobs_out: list[dict[str, Any]] = []
        for item in results:
            mode = (
                "api"
                if item.key in API_SOURCES
                else "rendered"
                if item.key in RENDERED_SOURCES
                else "none"
            )
            row = {
                "key": item.key,
                "label": COMPANY_LABELS.get(item.key, item.key),
                "mode": mode,
                "fetched": len(item.jobs),
                "created": 0,
                "updated": 0,
                "unchanged": 0,
                "error": item.error,
            }
            if item.jobs:
                source = self._source(item.key)
                for raw in item.jobs:
                    try:
                        outcome = upsert_raw_job(self._session, source, raw)
                    except Exception as exc:
                        row["error"] = f"{raw.title}: {exc}"
                        continue
                    if outcome.created:
                        created += 1
                        row["created"] += 1
                    elif outcome.updated:
                        updated += 1
                        row["updated"] += 1
                    else:
                        unchanged += 1
                        row["unchanged"] += 1
                    jobs_out.append(
                        {
                            "company": raw.company,
                            "title": raw.title,
                            "city": raw.city,
                            "job_type": raw.job_type,
                            "recruitment_program": raw.recruitment_program,
                            "source_url": raw.source_url,
                            "jd_length": len(raw.description or ""),
                            "requirements": len(raw.requirements),
                            # Lets a maintenance run report created/updated/
                            # unchanged instead of calling every hit new.
                            "outcome": (
                                "created"
                                if outcome.created
                                else "updated"
                                if outcome.updated
                                else "unchanged"
                            ),
                        }
                    )
            summary.append(row)

        self._session.commit()
        return {
            "keyword": keyword or "",
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "companies": summary,
            "jobs": jobs_out,
        }

    # --------------------------------------------------------------- fetching
    def _fetch(
        self, key: str, keyword: str | None, limit: int, project: str | None = None
    ) -> _Fetched:
        cache_key = (key, (keyword or "").strip().lower(), (project or "").strip())
        with _cache_lock:
            hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
            return _Fetched(key=key, jobs=hit[1][:limit])

        try:
            if key in API_SOURCES:
                jobs = self._fetch_api(key, keyword, limit, project)
            else:
                jobs = self._fetch_rendered(key, keyword, limit)
        except ConnectorError as exc:
            return _Fetched(key=key, jobs=[], error=str(exc))
        except Exception as exc:  # browser/runtime failures must stay contained
            return _Fetched(key=key, jobs=[], error=f"{type(exc).__name__}: {exc}")

        with _cache_lock:
            _cache[cache_key] = (time.monotonic(), jobs)
        return _Fetched(key=key, jobs=jobs)

    def _fetch_api(
        self, key: str, keyword: str | None, limit: int, project: str | None = None
    ) -> list[RawJob]:
        if key == "jd":
            return self._fetch_jd(keyword, limit)
        if key != "tencent":
            return []
        connector = TencentCampusConnector(self._settings)
        try:
            rows = connector.search(keyword, project=project or "日常实习", page_size=100)
            jobs: list[RawJob] = []
            for row in rows[:limit]:
                post_id = str(row.get("postId") or "").strip()
                if not post_id:
                    continue
                try:
                    jobs.append(connector.to_raw_job(connector.detail(post_id)))
                except ConnectorError:
                    continue
            return jobs
        finally:
            connector.close()

    def _fetch_jd(self, keyword: str | None, limit: int) -> list[RawJob]:
        connector = JdCampusConnector()
        try:
            rows = connector.search(keyword, page_size=max(limit, 10))
            jobs: list[RawJob] = []
            for row in rows[:limit]:
                try:
                    jobs.append(connector.to_raw_job(row))
                except ConnectorError:
                    continue
            return jobs
        finally:
            connector.close()

    def _fetch_rendered(self, key: str, keyword: str | None, limit: int) -> list[RawJob]:
        spec = RENDERED_SOURCES[key]
        search = RenderedJobSearch(self._settings)
        ok, message = search.available()
        if not ok:
            raise AppError("RENDER_UNAVAILABLE", message, status_code=503)
        return search.search(spec, keyword, limit)

    # ------------------------------------------------------------------ model
    def _source(self, key: str) -> JobSource:
        source_type = API_SOURCES[key] if key in API_SOURCES else RENDERED_SOURCES[key].source_type
        source = self._session.scalar(select(JobSource).where(JobSource.source_type == source_type))
        if source is None:
            source = JobSource(
                source_type=source_type,
                source_key=source_type,
                config_json={"mode": "official", "company": key},
                enabled=False,  # user-triggered only
            )
            self._session.add(source)
            self._session.flush()
        return source
