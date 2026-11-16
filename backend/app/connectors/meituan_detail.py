"""Meituan posting detail through its public JSON endpoint.

The rendered page is usable but its ``document.title`` is the site name
("职位详情 | 美团招聘"), which used to become the job title. The same page calls
``/api/official/job/getJobDetail`` with the ``jobUnionId`` from the URL and gets
structured fields — name, department, city, publish time, duty and requirement —
so prefer that over DOM scraping.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DETAIL_URL = "https://zhaopin.meituan.com/api/official/job/getJobDetail"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def job_union_id(url: str) -> str | None:
    """``?jobUnionId=4592562550`` → ``"4592562550"``."""
    values = parse_qs(urlsplit(url).query).get("jobUnionId") or []
    value = values[0].strip() if values else ""
    return value if value.isdigit() else None


def _first_name(items: Any) -> str | None:
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    return name
    if isinstance(items, str) and items.strip():
        return items.strip()
    return None


def _published_at(value: Any) -> datetime | None:
    """Meituan sends epoch milliseconds."""
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    if raw <= 0:
        return None
    seconds = raw / 1000 if raw > 10_000_000_000 else raw
    return datetime.fromtimestamp(seconds, tz=UTC)


def _job_type(data: dict[str, Any]) -> str | None:
    text = f"{data.get('jobType') or ''}{data.get('recruitType') or ''}".lower()
    if "实习" in text or "intern" in text:
        return "internship"
    if "校" in text or "campus" in text or "应届" in text:
        return "campus"
    if text:
        return "experienced"
    return None


def fetch_detail(settings: Settings, url: str) -> dict[str, Any] | None:
    """Return a page-like snapshot dict, or ``None`` when it cannot be read."""
    union_id = job_union_id(url)
    if union_id is None:
        return None
    try:
        response = httpx.post(
            DETAIL_URL,
            json={"jobUnionId": int(union_id)},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=min(settings.search_timeout_seconds, 20),
        )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("meituan_detail_failed", extra={"error": str(exc)[:200]})
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    title = str(data.get("name") or "").strip() or None
    duty = str(data.get("jobDuty") or "").strip()
    requirement = str(data.get("jobRequirement") or "").strip()
    if not title or not (duty or requirement):
        return None

    parts = [part for part in (duty, requirement) if part]
    description = "\n\n".join(parts)
    requirements = [
        line.strip() for line in requirement.replace("\r", "").splitlines() if line.strip()
    ]
    city = _first_name(data.get("cityList"))

    return {
        "title": title,
        "description": description,
        "requirements": requirements,
        "department": _first_name(data.get("department")),
        "job_category": str(data.get("jobFamily") or "").strip() or None,
        "city": city.removesuffix("市") if city else None,
        "location_text": city,
        "published_at": _published_at(data.get("firstPostTime")),
        "job_type": _job_type(data),
    }
