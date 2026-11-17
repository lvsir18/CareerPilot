"""On-demand Tavily Extract integration for a single verified job URL.

Extraction is deliberately not a crawler: one URL per user action, a daily
budget, Redis cache, explicit source classification, and no fallback to an
unverified page. A failed extraction never changes the JobLead.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from redis import Redis
from redis.exceptions import RedisError

from app.core.cache import get_redis
from app.core.config import Settings
from app.search.domains import classify_url

TAVILY_EXTRACT_ENDPOINT = "https://api.tavily.com/extract"


@dataclass(slots=True)
class ExtractedPage:
    url: str
    success: bool
    content: str | None = None
    error: str | None = None
    cached: bool = False
    credits_estimated: int = 0


class TavilyExtractService:
    def __init__(
        self,
        settings: Settings,
        *,
        redis_client: Redis | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client or get_redis()
        self._client = client or httpx.Client(
            timeout=settings.tavily_extract_timeout_seconds,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def _cache_key(self, url: str) -> str:
        return (
            "cp:extract:cache:"
            + hashlib.sha256(f"{self._settings.tavily_extract_depth}|{url}".encode()).hexdigest()
        )

    def _cache_get(self, url: str) -> str | None:
        if self._settings.tavily_extract_cache_ttl_seconds <= 0:
            return None
        try:
            raw = self._redis.get(self._cache_key(url))
        except RedisError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            content = payload.get("content")
            return content if isinstance(content, str) else None
        except (ValueError, TypeError):
            return None

    def _cache_set(self, url: str, content: str) -> None:
        if self._settings.tavily_extract_cache_ttl_seconds <= 0:
            return
        try:
            self._redis.set(
                self._cache_key(url),
                json.dumps({"content": content}, ensure_ascii=False),
                ex=self._settings.tavily_extract_cache_ttl_seconds,
            )
        except RedisError:
            return

    def _rate_allowed(self, user_id: UUID | None) -> bool:
        try:
            actor = str(user_id) if user_id else "anonymous"
            key = f"cp:extract:rate:{actor}:{int(time.time() // 60)}"
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, 90)
            count, _ = pipeline.execute()
            return int(count) <= self._settings.search_rate_limit_per_minute
        except Exception:
            # Like search rate limiting, fail open on Redis outage; the daily
            # budget is a second line of defence.
            return True

    def _budget_allowed(self) -> bool:
        try:
            day = datetime.now(UTC).date().isoformat()
            key = f"cp:extract:budget:{day}"
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, 172800)
            count, _ = pipeline.execute()
            return int(count) <= self._settings.tavily_extract_daily_budget
        except Exception:
            return True

    def extract(self, url: str, *, user_id: UUID | None = None) -> ExtractedPage:
        try:
            classified = classify_url(url)
        except ValueError as exc:
            return ExtractedPage(url=url, success=False, error=f"URL 不可提取：{exc}")

        cached = self._cache_get(classified.url)
        if cached is not None:
            return ExtractedPage(
                url=classified.url,
                success=True,
                content=cached,
                cached=True,
                credits_estimated=0,
            )
        if not self._settings.tavily_api_key:
            return ExtractedPage(
                url=classified.url,
                success=False,
                error="TAVILY_API_KEY 未配置，无法提取官方详情",
            )
        if not self._rate_allowed(user_id):
            return ExtractedPage(
                url=classified.url,
                success=False,
                error="详情提取频率已达上限，请稍后再试",
            )
        if not self._budget_allowed():
            return ExtractedPage(
                url=classified.url,
                success=False,
                error="详情提取达到每日预算，请稍后再试",
            )
        try:
            response = self._client.post(
                TAVILY_EXTRACT_ENDPOINT,
                json={
                    "api_key": self._settings.tavily_api_key,
                    "urls": [classified.url],
                    "extract_depth": self._settings.tavily_extract_depth,
                    "include_images": False,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException:
            return ExtractedPage(url=classified.url, success=False, error="Tavily Extract 超时")
        except httpx.TransportError:
            return ExtractedPage(url=classified.url, success=False, error="Tavily Extract 网络错误")
        if response.status_code == 429:
            return ExtractedPage(
                url=classified.url,
                success=False,
                error="Tavily Extract 配额已耗尽",
                credits_estimated=1,
            )
        if response.status_code >= 400:
            return ExtractedPage(
                url=classified.url,
                success=False,
                error=f"Tavily Extract 返回 HTTP {response.status_code}",
                credits_estimated=1,
            )
        try:
            payload: Any = response.json()
        except ValueError:
            return ExtractedPage(
                url=classified.url,
                success=False,
                error="Tavily Extract 返回非 JSON",
                credits_estimated=1,
            )
        results = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                content = item.get("raw_content") or item.get("content")
                if isinstance(content, str) and content.strip():
                    content = content[:100_000]
                    self._cache_set(classified.url, content)
                    return ExtractedPage(
                        url=classified.url,
                        success=True,
                        content=content,
                        credits_estimated=1,
                    )
        failed = payload.get("failed_results") if isinstance(payload, dict) else None
        reason = "Tavily Extract 未返回可用正文"
        if isinstance(failed, list) and failed and isinstance(failed[0], dict):
            reason = str(failed[0].get("error") or failed[0].get("reason") or reason)[:300]
        return ExtractedPage(
            url=classified.url,
            success=False,
            error=reason,
            credits_estimated=1,
        )
