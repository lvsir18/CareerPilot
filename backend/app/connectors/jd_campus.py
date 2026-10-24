"""JD (京东) campus recruitment public JSON API.

The campus site is a SPA, but its own list endpoint is a plain POST with a JSON
body and returns responsibilities/requirements inline — no signature, no login.
Rendering the page is therefore unnecessary; calling the endpoint is faster and
far more stable than the browser route.

Probed 2026-10-24::

    POST https://campus.jd.com/api/wx/position/page?type=present
    {"pageSize":10,"pageIndex":0,
     "parameter":{"positionName":"算法","planIdList":[],
                  "jobDirectionCodeList":[],"workCityCodeList":[],
                  "positionDeptList":[]}}
    -> {"success": true, "body": {"totalNumber": 12, "items": [...]}}

``parameter.positionName`` is the keyword filter. The list carries no city and no
detail URL, so ``city`` stays empty and the source link points at the list page —
inventing either would be worse than leaving them blank.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.connectors.errors import ConnectorHTTPError, ConnectorParseError
from app.connectors.schemas import RawJob
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus

LIST_URL = "https://campus.jd.com/api/wx/position/page?type=present"
LIST_PAGE = "https://campus.jd.com/#/jobs"
SOURCE_TYPE = "jd_campus"
SOURCE_KEY = "jd-campus"
COMPANY = "京东"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

MAX_PAGE_SIZE = 50


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    cleaned = []
    for part in value.replace("\r\n", "\n").split("\n"):
        text = part.strip().strip("•·-—").strip()
        if text:
            cleaned.append(text)
    return cleaned[:20]


def _published_at(value: Any) -> datetime | None:
    """JD ships epoch milliseconds; anything else is left empty on purpose."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
    except (ValueError, OSError):
        return None


class JdCampusConnector:
    """Minimal client for the public campus position list."""

    def __init__(self, timeout: float = 25.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
                "Referer": "https://campus.jd.com/",
            },
        )

    def close(self) -> None:
        self._client.close()

    def search(self, keyword: str | None = None, *, page_size: int = 20) -> list[dict[str, Any]]:
        body = {
            "pageSize": max(1, min(page_size, MAX_PAGE_SIZE)),
            "pageIndex": 0,
            "parameter": {
                "positionName": (keyword or "").strip(),
                "planIdList": [],
                "jobDirectionCodeList": [],
                "workCityCodeList": [],
                "positionDeptList": [],
            },
        }
        try:
            response = self._client.post(LIST_URL, json=body)
        except httpx.HTTPError as exc:
            raise ConnectorHTTPError(f"京东招聘接口请求失败：{type(exc).__name__}") from exc
        if response.status_code != 200:
            raise ConnectorHTTPError(
                f"京东招聘接口返回 {response.status_code}", status_code=response.status_code
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorParseError("京东招聘接口返回的不是 JSON") from exc
        if not payload.get("success"):
            raise ConnectorParseError("京东招聘接口返回失败状态")
        items = (payload.get("body") or {}).get("items") or []
        if not isinstance(items, list):
            raise ConnectorParseError("京东招聘接口缺少岗位列表")
        return [item for item in items if isinstance(item, dict)]

    def to_raw_job(self, item: dict[str, Any], *, fetched_at: datetime | None = None) -> RawJob:
        position_id = _text(item.get("publishId"))
        title = _text(item.get("positionName"))
        if not position_id:
            raise ConnectorParseError("京东岗位缺少 publishId")
        if not title:
            raise ConnectorParseError("京东岗位缺少名称")
        now = fetched_at or datetime.now(UTC)
        direction = _text(item.get("jobDirection"))
        plan = _text(item.get("planName"))

        return RawJob(
            source_type=SOURCE_TYPE,
            source_key=SOURCE_KEY,
            source_job_id=position_id,
            company=COMPANY,
            title=title,
            # The list has no per-job detail route that survives a hash reload, so
            # the list page is the honest link.
            source_url=LIST_PAGE,
            description=_text(item.get("workContent")),
            department=direction,
            location_text=None,
            city=None,
            job_type="internship" if "实习" in title else "campus",
            recruitment_program=plan or "校园招聘",
            requirements=_split_lines(_text(item.get("qualification"))),
            published_at=_published_at(item.get("publishTime")),
            fetched_at=now,
            raw_payload={
                "publishId": position_id,
                "reqId": item.get("reqId"),
                "jobDirection": direction,
                "positionTypeName": item.get("positionTypeName"),
                "planName": plan,
            },
            is_demo=False,
            # ``type=present`` on the endpoint already means "currently open".
            status=JobStatus.OPEN,
            source_method=JobSourceMethod.API,
            verification_status=VerificationStatus.VERIFIED,
            verified_at=now,
        )
