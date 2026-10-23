"""Baidu public careers page connector (single user-submitted detail URL).

Verified 2026-10-21:
- ``https://talent.baidu.com/jobs/detail/INTERN/<postId>`` returns server-side
  HTML containing ``window.__INITIAL_DATA__`` with ``detailData.postInfo``.
- ``https://talent.baidu.com/robots.txt`` returns HTTP 404 (no rules declared).
- The page is publicly viewable without login.

The connector makes exactly one request per user-initiated import, uses the
shared SafeHttpClient (allow-list, SSRF protection, timeout, throttle) and does
not use undocumented JSON endpoints or bypass any access control.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.connectors.errors import ConnectorNotConfigured, ConnectorParseError
from app.connectors.http import SafeHttpClient
from app.connectors.schemas import ConnectorHealth, RawJob
from app.core.config import Settings
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus

ALLOWED_HOSTS = frozenset({"talent.baidu.com"})
DETAIL_PATH = re.compile(r"^/jobs/detail/(?P<recruit_type>[A-Z]+)/(?P<job_id>[0-9a-fA-F-]{36})/?$")
_INITIAL_DATA_MARKER = "window.__INITIAL_DATA__"


def _decode_initial_data(page: str) -> dict[str, Any]:
    index = page.find(_INITIAL_DATA_MARKER)
    if index < 0:
        raise ConnectorParseError("页面缺少 __INITIAL_DATA__，可能已下线或页面结构变更")
    remainder = page[index + len(_INITIAL_DATA_MARKER) :]
    equals = remainder.find("=")
    if equals < 0:
        raise ConnectorParseError("页面内嵌数据结构异常")
    remainder = remainder[equals + 1 :].lstrip()
    # Baidu's SSR payload contains JavaScript ``undefined`` values.
    remainder = re.sub(r"(?<=[:,\[])\s*undefined\s*(?=[,}\]])", "null", remainder)
    try:
        data, _ = json.JSONDecoder().raw_decode(remainder)
    except json.JSONDecodeError as exc:
        raise ConnectorParseError("页面内嵌数据不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise ConnectorParseError("页面内嵌数据顶层结构异常")
    return data


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _date_only(value: Any) -> datetime | None:
    """Official page provides a date, not a time; normalize to UTC midnight."""
    text = _text(value)
    if not text:
        return None
    try:
        date = datetime.fromisoformat(text[:10])
    except ValueError:
        return None
    return date.replace(tzinfo=UTC)


def _first_city(value: str | None) -> str | None:
    if not value:
        return None
    first = re.split(r"[,，、/]", value)[0].strip()
    first = first.removesuffix("市").removesuffix("省")
    return first or None


def parse_detail_html(
    page: str,
    *,
    requested_url: str,
    fetched_at: datetime | None = None,
) -> RawJob:
    data = _decode_initial_data(page)
    detail = data.get("detailData")
    if not isinstance(detail, dict):
        raise ConnectorParseError("页面缺少 detailData")
    if detail.get("isValid") is False:
        raise ConnectorParseError("该百度职位已下线或不可投递")
    post = detail.get("postInfo")
    if not isinstance(post, dict):
        raise ConnectorParseError("页面缺少 postInfo")

    post_id = _text(post.get("postId"))
    if not post_id:
        raise ConnectorParseError("职位缺少 postId")
    title = _text(post.get("name"))
    if not title:
        raise ConnectorParseError("职位缺少名称")

    path_match = DETAIL_PATH.match(urlsplit(requested_url).path)
    recruit_type = _text(detail.get("recruitType")) or (
        path_match.group("recruit_type") if path_match else None
    )
    project_type = _text(post.get("projectType"))
    job_type = _classify_job_type(recruit_type, project_type)
    work_place = _text(post.get("workPlace"))
    requirements = [
        line.strip()
        for line in (_text(post.get("serviceCondition")) or "").splitlines()
        if line.strip()
    ]
    now = fetched_at or datetime.now(UTC)
    canonical_url = f"https://talent.baidu.com/jobs/detail/{recruit_type or 'INTERN'}/{post_id}"

    return RawJob(
        source_type="baidu_public",
        source_key="baidu-public",
        source_job_id=post_id,
        company="百度",
        title=title,
        source_url=canonical_url,
        description=_text(post.get("workContent")),
        department=_text(post.get("orgName"))
        or _text(post.get("postType"))
        or _text(post.get("bgShortName")),
        location_text=work_place,
        city=_first_city(work_place),
        job_type=job_type,
        recruitment_program=project_type,
        requirements=requirements,
        published_at=_date_only(post.get("publishDate")),
        fetched_at=now,
        raw_payload=post,
        is_demo=False,
        status=JobStatus.OPEN,
        source_method=JobSourceMethod.PUBLIC_PAGE,
        verification_status=VerificationStatus.VERIFIED,
        verified_at=now,
    )


def _classify_job_type(recruit_type: str | None, project_type: str | None) -> str | None:
    material = f"{recruit_type or ''} {project_type or ''}"
    if "实习" in material or "INTERN" in material.upper():
        return "internship"
    if "校" in material or "GRADUATE" in material.upper():
        return "campus"
    if "社" in material or "SOCIETY" in material.upper():
        return "full_time"
    return None


class BaiduPublicConnector:
    source_type = "baidu_public"
    allowed_hosts = ALLOWED_HOSTS

    def __init__(self, settings: Settings, client: SafeHttpClient | None = None) -> None:
        self._settings = settings
        self._client = client or SafeHttpClient(
            allowed_hosts=set(ALLOWED_HOSTS),
            user_agent=settings.connector_user_agent,
            timeout_seconds=settings.connector_timeout_seconds,
            max_retries=0,  # one user-triggered request; no silent retries
            backoff_seconds=0,
            min_interval_seconds=settings.connector_min_interval_seconds,
            max_response_bytes=settings.connector_max_response_bytes,
        )

    def close(self) -> None:
        self._client.close()

    def validate_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "talent.baidu.com":
            raise ConnectorNotConfigured("仅支持 https://talent.baidu.com 的官方详情页")
        if not DETAIL_PATH.match(parsed.path):
            raise ConnectorNotConfigured("链接不是百度官方岗位详情页")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    def fetch_job_detail(self, url: str) -> RawJob:
        canonical = self.validate_url(url)
        page = self._client.get_text(canonical)
        return parse_detail_html(page, requested_url=canonical)

    def fetch_jobs(self, source_config: dict[str, Any]) -> list[RawJob]:
        # Deliberately not a bulk crawler. Scheduled/source sync is not enabled
        # for public pages; users import explicitly.
        raise ConnectorNotConfigured("公开网页来源仅支持用户提交单个岗位链接")

    def health_check(self, source_config: dict[str, Any]) -> ConnectorHealth:
        return ConnectorHealth(
            configured=True,
            ok=True,
            message="百度公开招聘详情页（单链接导入）；robots.txt 404，未声明抓取限制",
        )
