"""Tencent campus recruiting connector (``join.qq.com``).

Why this connector exists: the campus site is a SPA. Its HTML only carries
``<title>岗位详情 | 腾讯校招</title>``, so search results could never be verified
and Tencent always fell back to "candidate links". The site's own front-end
calls two public, unauthenticated JSON endpoints that return the full JD:

- ``POST /api/v1/position/searchPosition`` — keyword + recruiting project paging
- ``GET  /api/v1/jobDetails/getJobDetailsByPostId?postId=`` — one full JD

The recruiting project ("日常实习" / "应届实习" / "应届毕业生" / "青云计划-*") is a
source-provided field, so job type is read from Tencent instead of guessed.

Only user-initiated, bounded lookups happen here (one result page + at most
``limit`` details). There is no crawl queue, paging loop, login or cookie reuse.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.connectors.errors import ConnectorParseError
from app.connectors.http import SafeHttpClient
from app.connectors.schemas import ConnectorHealth, RawJob
from app.core.config import Settings
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus

API_HOST = "join.qq.com"
SEARCH_URL = f"https://{API_HOST}/api/v1/position/searchPosition"
DETAIL_URL = f"https://{API_HOST}/api/v1/jobDetails/getJobDetailsByPostId"
DETAIL_PAGE_PREFIX = f"https://{API_HOST}/post_detail.html?postid="

# Project ids come from ``/api/v1/position/getAllProject``; names are what the
# site shows in its own filter dropdown.
PROJECTS: dict[str, int] = {
    "日常实习": 4,
    "应届实习": 2,
    "应届毕业生": 1,
    "青云计划-应届生": 14,
    "青云计划-实习生": 20,
}
DEFAULT_PROJECT = "日常实习"

_LINE_SPLIT = re.compile(r"\r?\n+")


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status")
    if status not in (0, "0"):
        message = _text(payload.get("message")) or f"status={status}"
        raise ConnectorParseError(f"腾讯校招接口返回异常：{message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ConnectorParseError("腾讯校招接口缺少 data")
    return data


def _primary_city(cities: list[str] | None) -> str | None:
    for item in cities or []:
        text = _text(item)
        if not text:
            continue
        # The site writes "深圳总部"; the library stores plain city names.
        return text.removesuffix("总部").removesuffix("市") or text
    return None


def classify_job_type(project_name: str | None) -> str | None:
    if not project_name:
        return None
    if "实习" in project_name:
        return "internship"
    if "应届" in project_name or "校" in project_name:
        return "campus"
    return None


def _split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in _LINE_SPLIT.split(value) if line.strip()]


class TencentCampusConnector:
    source_type = "tencent_campus"

    def __init__(self, settings: Settings, client: SafeHttpClient | None = None) -> None:
        self._settings = settings
        self._client = client or SafeHttpClient(
            allowed_hosts={API_HOST},
            user_agent=settings.connector_user_agent,
            timeout_seconds=settings.connector_timeout_seconds,
            max_retries=1,
            backoff_seconds=0.5,
            min_interval_seconds=settings.connector_min_interval_seconds,
            max_response_bytes=settings.connector_max_response_bytes,
        )

    def close(self) -> None:
        self._client.close()

    def search(
        self,
        keyword: str | None,
        *,
        project: str = DEFAULT_PROJECT,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "keyword": (keyword or "").strip()[:30],
            "workCountryType": 1,
            "pageIndex": 1,
            "pageSize": max(1, min(page_size, 100)),
        }
        data = _unwrap(self._client.post_json(SEARCH_URL, payload))
        positions = data.get("positionList")
        # A zero-result query answers ``{"positionList": null, "count": 0}``
        # instead of an empty list, so ``null`` means "no match", not "broken
        # schema" (that used to surface as a TOOL_FAILED agent step).
        if positions is None:
            return []
        if not isinstance(positions, list):
            raise ConnectorParseError("腾讯校招搜索结果 positionList 格式异常")
        rows = [item for item in positions if isinstance(item, dict)]
        # ``projectId`` is accepted but ignored by the endpoint (campus postings
        # come back regardless), so the recruiting project is filtered locally.
        return [row for row in rows if _text(row.get("projectName")) == project]

    def detail(self, post_id: str) -> dict[str, Any]:
        return _unwrap(self._client.get_json(f"{DETAIL_URL}?postId={post_id}"))

    def to_raw_job(self, detail: dict[str, Any], *, fetched_at: datetime | None = None) -> RawJob:
        post_id = _text(detail.get("postId"))
        title = _text(detail.get("title"))
        if not post_id:
            raise ConnectorParseError("腾讯岗位缺少 postId")
        if not title:
            raise ConnectorParseError("腾讯岗位缺少名称")

        project = _text(detail.get("projectName")) or _text(detail.get("recruitLabelName"))
        cities = [city for city in (detail.get("workCityList") or []) if _text(city)]
        department = None
        bgs = detail.get("intentionBGDList")
        if isinstance(bgs, list) and bgs and isinstance(bgs[0], dict):
            department = _text(bgs[0].get("showTitle")) or _text(bgs[0].get("title"))
        department = department or _text(detail.get("tidName"))
        now = fetched_at or datetime.now(UTC)

        return RawJob(
            source_type=self.source_type,
            source_key="tencent-campus",
            source_job_id=post_id,
            company="腾讯",
            title=title,
            source_url=f"{DETAIL_PAGE_PREFIX}{post_id}",
            description=_text(detail.get("desc")),
            department=department,
            location_text=" ".join(cities) if cities else None,
            city=_primary_city(cities),
            job_type=classify_job_type(project),
            recruitment_program=project,
            requirements=_split_lines(_text(detail.get("request"))),
            # The API exposes no publish date; leaving it empty is required —
            # never invent one.
            published_at=None,
            fetched_at=now,
            raw_payload={
                "postId": post_id,
                "title": title,
                "projectId": detail.get("projectId"),
                "projectName": project,
                "tidName": detail.get("tidName"),
                "workCityList": cities,
            },
            is_demo=False,
            status=JobStatus.OPEN,
            source_method=JobSourceMethod.API,
            verification_status=VerificationStatus.VERIFIED,
            verified_at=now,
        )

    def health_check(self, source_config: dict[str, Any]) -> ConnectorHealth:
        return ConnectorHealth(
            configured=True,
            ok=True,
            message="腾讯校招官方 JSON 接口（join.qq.com），公开可访问，无需登录",
        )
