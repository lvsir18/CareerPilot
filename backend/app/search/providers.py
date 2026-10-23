"""Tavily search provider and the Baidu official-list fallback.

Tavily is the only licensed search API in this build. It requires an
operator-supplied ``TAVILY_API_KEY``. Search results are candidate links only;
the Baidu provider reads one public list page and is not a licensed API.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.connectors.baidu import _decode_initial_data
from app.connectors.http import SafeHttpClient
from app.core.config import Settings
from app.search.base import (
    SearchError,
    SearchHit,
    SearchNotConfigured,
    SearchProviderError,
)
from app.search.domains import resolve_company

TAVILY_ENDPOINT = "https://api.tavily.com/search"


class TavilySearchProvider:
    """Tavily Search API.

    Only URLs/titles/short snippets are retained. Do not treat Tavily content as
    a full job description or as verification of an official job.
    """

    name = "tavily"
    label = "Tavily Search API"
    role = "primary"
    available = True
    cost_note = "按 Tavily 当前 plan 的 credits 计费；未配置 key 时不发请求"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._key = settings.tavily_api_key
        self._depth = settings.tavily_search_depth
        self._max_results = settings.tavily_max_results
        self._client = client or httpx.Client(
            timeout=settings.search_timeout_seconds, follow_redirects=False
        )

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def close(self) -> None:
        self._client.close()

    def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]:
        if not self.configured:
            raise SearchNotConfigured("Tavily API key 未配置")
        try:
            response = self._client.post(
                TAVILY_ENDPOINT,
                json={
                    "api_key": self._key,
                    "query": text,
                    "topic": "general",
                    "search_depth": self._depth,
                    "max_results": min(max(limit, 1), self._max_results),
                    "include_domains": domains,
                    "include_domains_mode": "restrict",
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_published_date": True,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise SearchError("Tavily 搜索超时", retryable=True) from exc
        except httpx.TransportError as exc:
            raise SearchError("Tavily 网络错误", retryable=True) from exc
        if response.status_code == 429:
            raise SearchError("Tavily 搜索配额已耗尽", retryable=False)
        if response.status_code >= 400:
            raise SearchProviderError(f"Tavily 返回 HTTP {response.status_code}")
        payload = response.json()
        hits: list[SearchHit] = []
        for rank, item in enumerate(payload.get("results") or []):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            hits.append(
                SearchHit(
                    title=str(item.get("title") or ""),
                    url=str(item["url"]),
                    snippet=_snippet(item.get("content")),
                    # Tavily's published_date is a web-index date, not the
                    # employer's official JD publication date. Keep it unknown.
                    published_date=None,
                    rank=rank,
                    provider=self.name,
                )
            )
        return hits


class BaiduOfficialListProvider:
    """Read one public Baidu list page; not a licensed search API."""

    name = "baidu_official_list"
    label = "百度官方公开列表页"
    role = "fallback"
    available = True
    configured = True
    cost_note = "公开页面，无 API 费用；只读第一页，不做批量翻页"

    def __init__(self, settings: Settings, client: SafeHttpClient | None = None) -> None:
        self._client = client or SafeHttpClient(
            allowed_hosts={"talent.baidu.com"},
            user_agent=settings.connector_user_agent,
            timeout_seconds=settings.search_timeout_seconds,
            max_retries=0,
            backoff_seconds=0,
            min_interval_seconds=settings.connector_min_interval_seconds,
            max_response_bytes=settings.connector_max_response_bytes,
        )

    def close(self) -> None:
        self._client.close()

    def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]:
        if "talent.baidu.com" not in domains:
            return []
        recruit_type = (
            "GRADUATE"
            if any(word in text for word in ("校招", "秋招", "春招", "校园"))
            else "INTERN"
        )
        url = f"https://talent.baidu.com/jobs/list?recruitType={recruit_type}"
        try:
            page = self._client.get_text(url)
            data = _decode_initial_data(page)
        except Exception as exc:
            if isinstance(exc, SearchError):
                raise
            raise SearchProviderError("百度官方列表页暂时不可用") from exc
        list_data = data.get("listData")
        if not isinstance(list_data, dict):
            raise SearchProviderError("百度列表数据结构异常")
        items = list_data.get("listDetailData") or []
        hits: list[SearchHit] = []
        for rank, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            post_id = str(item.get("postId") or "").strip()
            title = str(item.get("name") or "").strip()
            if not post_id or not title:
                continue
            project = str(item.get("projectType") or "").strip()
            city_text = str(item.get("workPlace") or "").strip()
            city = city_text.split(",")[0].strip().removesuffix("市").removesuffix("省") or None
            published = _parse_date(item.get("publishDate"))
            hits.append(
                SearchHit(
                    title=title,
                    url=f"https://talent.baidu.com/jobs/detail/{recruit_type}/{post_id}",
                    snippet=f"{project} · {city_text}".strip(" ·"),
                    company="baidu",
                    city=city,
                    job_type=_baidu_job_type(recruit_type, project),
                    published_date=published,
                    rank=rank,
                    provider=self.name,
                )
            )
        return hits[:limit]


def _snippet(value: Any, limit: int = 1_000) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] or None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_search_date(value: Any) -> date | None:
    """Only accept explicit ISO dates; never infer from relative text."""
    return _parse_date(value)


def _baidu_job_type(recruit_type: str, project: str) -> str | None:
    material = f"{recruit_type} {project}"
    if "实习" in material or "INTERN" in material.upper():
        return "internship"
    if "校" in material or "GRADUATE" in material.upper():
        return "campus"
    return None


def build_search_provider(settings: Settings, client: httpx.Client | None = None) -> Any:
    """Build Tavily only when explicitly selected; it still needs a key."""
    if settings.search_provider == "tavily":
        return TavilySearchProvider(settings, client=client)
    return None


def company_key_from_hit(hit: SearchHit) -> str | None:
    if hit.company:
        return resolve_company(hit.company)
    host = (urlsplit(hit.url).hostname or "").lower()
    from app.search.domains import company_for_host

    return company_for_host(host)
