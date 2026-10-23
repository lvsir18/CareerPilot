"""Discovery orchestration: Tavily plus the Baidu official-list fallback."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from app.core.cache import get_redis
from app.core.config import Settings
from app.core.logging import get_logger
from app.search.base import (
    CompanySearchDiagnostic,
    SearchError,
    SearchHit,
    SearchNotConfigured,
    SearchOutcome,
    SearchProvider,
    SearchProviderInfo,
)
from app.search.domains import (
    COMPANY_DOMAINS,
    COMPANY_NAMES,
    classify_url,
    inspect_url,
    search_domains_for,
)
from app.search.providers import (
    BaiduOfficialListProvider,
    TavilySearchProvider,
    build_search_provider,
)
from app.search.taxonomy import classify_job_family

logger = get_logger(__name__)

_OFFICIAL_PROVIDER = "baidu_official_list"
_PROVIDER_ERROR_MARKERS = ("超时", "错误", "失败", "配额", "不可用")


class SearchService:
    def __init__(
        self,
        settings: Settings,
        *,
        redis_client: Redis | None = None,
        provider: SearchProvider | None = None,
        providers: list[SearchProvider] | None = None,
        official_provider: Any | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client or get_redis()
        if providers is not None:
            self._providers = providers
        elif provider is not None:
            self._providers = [provider]
        else:
            built = build_search_provider(settings)
            self._providers = [built] if built is not None else []
        self._official = (
            official_provider
            if official_provider is not None
            else (
                BaiduOfficialListProvider(settings)
                if settings.official_site_discovery_enabled
                else None
            )
        )

    def close(self) -> None:
        for provider in [*self._providers, self._official]:
            close = getattr(provider, "close", None)
            if callable(close):
                close()

    def provider_infos(self) -> list[SearchProviderInfo]:
        """Expose Tavily/Baidu status without making network calls."""
        tavily_configured = bool(self._settings.tavily_api_key)
        tavily_enabled = any(provider.name == "tavily" for provider in self._providers)
        return [
            SearchProviderInfo(
                name=TavilySearchProvider.name,
                label=TavilySearchProvider.label,
                role=TavilySearchProvider.role,
                configured=tavily_configured,
                available=tavily_configured and tavily_enabled,
                enabled=tavily_enabled,
                reason=(
                    None
                    if tavily_configured and tavily_enabled
                    else (
                        "未启用 Tavily"
                        if not tavily_enabled
                        else "未配置 TAVILY_API_KEY，未发起请求"
                    )
                ),
                cost_note=TavilySearchProvider.cost_note,
            ),
            SearchProviderInfo(
                name=_OFFICIAL_PROVIDER,
                label=BaiduOfficialListProvider.label,
                role=BaiduOfficialListProvider.role,
                configured=self._official is not None,
                available=self._official is not None,
                enabled=self._official is not None,
                reason=(
                    None if self._official is not None else "OFFICIAL_SITE_DISCOVERY_ENABLED=false"
                ),
                cost_note=BaiduOfficialListProvider.cost_note,
            ),
        ]

    def _rate_allowed(
        self,
        provider_name: str,
        warnings: list[str],
        user_id: UUID | None = None,
    ) -> bool:
        try:
            actor = str(user_id) if user_id else "anonymous"
            key = f"cp:search:rate:{provider_name}:{actor}:{int(time.time() // 60)}"
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, 90)
            count, _ = pipeline.execute()
            if int(count) > self._settings.search_rate_limit_per_minute:
                warnings.append(f"{provider_name} 搜索频率已达上限，请稍后再试")
                return False
        except RedisError:
            warnings.append("搜索限流组件暂不可用，本次未限流")
        except Exception:
            warnings.append("搜索限流组件暂不可用，本次未限流")
        return True

    def _daily_budget_allowed(self, provider_name: str, warnings: list[str]) -> bool:
        """Count only actual outbound calls, not cache hits."""
        try:
            day = datetime.now(UTC).date().isoformat()
            key = f"cp:search:budget:{provider_name}:{day}"
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, 172800)
            count, _ = pipeline.execute()
            if int(count) > self._settings.search_daily_budget_per_provider:
                warnings.append(f"{provider_name} 达到每日请求预算，已跳过")
                return False
        except RedisError:
            warnings.append("搜索预算组件暂不可用，本次未限流")
        except Exception:
            warnings.append("搜索预算组件暂不可用，本次未限流")
        return True

    def _cache_get(self, key: str) -> list[SearchHit] | None:
        if self._settings.search_cache_ttl_seconds <= 0:
            return None
        try:
            raw = self._redis.get(key)
        except RedisError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            hits = []
            for item in payload:
                published = item.get("published_date")
                if published:
                    item["published_date"] = date.fromisoformat(published)
                hits.append(SearchHit(**item))
            return hits
        except (ValueError, TypeError):
            return None

    def _cache_set(self, key: str, hits: list[SearchHit]) -> None:
        if self._settings.search_cache_ttl_seconds <= 0:
            return
        try:
            payload = json.dumps(
                [
                    {
                        **asdict(hit),
                        "published_date": hit.published_date.isoformat()
                        if hit.published_date
                        else None,
                    }
                    for hit in hits
                ],
                ensure_ascii=False,
            )
            self._redis.set(key, payload, ex=self._settings.search_cache_ttl_seconds)
        except RedisError:
            return

    def _call_provider(
        self,
        provider: SearchProvider,
        text: str,
        domains: list[str],
        limit: int,
        warnings: list[str],
        user_id: UUID | None = None,
    ) -> tuple[list[SearchHit], bool, bool]:
        if not getattr(provider, "available", True):
            reason = getattr(provider, "retired_reason", "该搜索服务不可用")
            warnings.append(f"{getattr(provider, 'label', provider.name)}：{reason}")
            return [], False, False
        if not provider.configured:
            warnings.append(f"{provider.name} 搜索服务未配置")
            return [], False, False
        if not self._rate_allowed(provider.name, warnings, user_id):
            return [], False, False
        cache_key = (
            "cp:search:cache:"
            + hashlib.sha256(
                f"{provider.name}|{text}|{','.join(domains)}|{limit}".encode()
            ).hexdigest()
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached, True, False
        if not self._daily_budget_allowed(provider.name, warnings):
            return [], False, False
        try:
            hits = provider.search(text, domains, limit)
        except SearchNotConfigured as exc:
            warnings.append(exc.message)
            return [], False, False
        except SearchError as exc:
            warnings.append(f"{provider.name}: {exc.message}")
            return [], False, False
        except Exception as exc:  # provider must never break database results
            logger.warning(
                "search_provider_failed",
                extra={"provider": provider.name, "error_type": type(exc).__name__},
            )
            warnings.append(f"{provider.name}: 搜索服务暂时不可用")
            return [], False, False
        for hit in hits:
            hit.provider = provider.name
            if not hit.providers:
                hit.providers = [provider.name]
        self._cache_set(cache_key, hits)
        return hits, False, True

    def _merge_hits(self, hits: list[SearchHit]) -> list[SearchHit]:
        """Canonical-URL dedupe preserving provider/source evidence."""
        grouped: dict[str, list[SearchHit]] = {}
        order: list[str] = []
        for hit in hits:
            try:
                official = classify_url(hit.url)
            except ValueError:
                continue
            if official.url not in grouped:
                grouped[official.url] = []
                order.append(official.url)
            hit.url = official.url
            hit.company = official.company
            hit.url_type = official.url_type
            hit.source_kind = official.source_kind
            hit.trusted_tenant = official.tenant_host
            grouped[official.url].append(hit)

        fused: list[SearchHit] = []
        for url in order:
            variants = grouped[url]
            variants.sort(key=lambda item: (item.rank, -(len(item.snippet or ""))))
            best = variants[0]
            providers = list(
                dict.fromkeys(
                    provider
                    for item in variants
                    for provider in (item.providers or ([item.provider] if item.provider else []))
                )
            )
            best.providers = providers
            best.provider = providers[0] if providers else best.provider
            best.rank = min(item.rank for item in variants)
            fused.append(best)
        fused.sort(key=lambda item: (item.rank, -len(item.providers), item.url))
        return fused

    def _query_terms(self, text: str) -> list[str]:
        parts = [part.strip() for part in re.split(r"[|;；\n]", text) if part.strip()]
        return (parts or [text.strip()])[: self._settings.tavily_max_query_terms]

    def _run_task(
        self,
        company: str,
        text: str,
        domains: list[str],
        layer: str,
        limit: int,
        warnings: list[str],
        user_id: UUID | None,
    ) -> tuple[list[SearchHit], int, int, int, bool, list[str]]:
        hits: list[SearchHit] = []
        queries = 0
        cached_queries = 0
        credits = 0
        had_error = False
        used_providers: list[str] = []
        for provider in self._providers:
            before = len(warnings)
            provider_hits, was_cached, outbound_called = self._call_provider(
                provider, text, domains, limit, warnings, user_id
            )
            if provider.configured and getattr(provider, "available", True):
                if outbound_called or was_cached:
                    queries += 1
                if was_cached:
                    cached_queries += 1
                if provider.name == "tavily" and outbound_called:
                    credits += 1
            if provider_hits:
                used_providers.append(provider.name)
            if len(warnings) > before and any(
                marker in warning
                for warning in warnings[before:]
                for marker in _PROVIDER_ERROR_MARKERS
            ):
                had_error = True
            for hit in provider_hits:
                hit.search_layer = layer
            hits.extend(provider_hits)
        return hits, queries, cached_queries, credits, had_error, used_providers

    def search(
        self,
        text: str,
        *,
        company_keys: list[str],
        city: str | None = None,
        job_type: str | None = None,
        job_family: str | None = None,
        limit: int | None = None,
        user_id: UUID | None = None,
    ) -> SearchOutcome:
        limit = min(limit or self._settings.search_max_results, self._settings.search_max_results)
        selected = list(dict.fromkeys(company_keys or list(COMPANY_DOMAINS)))
        warnings: list[str] = []
        hits: list[SearchHit] = []
        providers_used: list[str] = []
        provider_queries = 0
        cached_queries = 0
        credits_estimated = 0
        terms = self._query_terms(text)
        diagnostics = {company: CompanySearchDiagnostic(company=company) for company in selected}
        layers_by_company: dict[str, set[str]] = {company: set() for company in selected}

        tasks: list[tuple[str, str, str, list[str]]] = []
        for company in selected:
            domains = search_domains_for([company])
            if not domains:
                continue
            for term in terms:
                tasks.append((company, term, "exact", domains))
        max_queries = min(
            self._settings.search_max_queries_per_request,
            self._settings.tavily_max_queries_per_request,
        )
        if len(tasks) > max_queries:
            warnings.append(f"查询数超过上限，仅执行前 {max_queries} 个企业/关键词任务")
            tasks = tasks[:max_queries]

        executed_queries = 0

        def run(company: str, query_text: str, layer: str, domains: list[str]) -> None:
            nonlocal provider_queries, cached_queries, credits_estimated, executed_queries
            raw_hits, queries, cached, credits, had_error, used = self._run_task(
                company,
                query_text,
                domains,
                layer,
                limit,
                warnings,
                user_id,
            )
            diag = diagnostics[company]
            diag.queries += queries
            diag.provider_errors += 1 if had_error else 0
            layers_by_company[company].add(layer)
            executed_queries += queries
            provider_queries += queries
            cached_queries += cached
            credits_estimated += credits
            for name in used:
                if name not in providers_used:
                    providers_used.append(name)
            for hit in raw_hits:
                diag.raw_results += 1
                analyzed = inspect_url(hit.url)
                if analyzed is None:
                    diag.dropped_invalid += 1
                    continue
                if analyzed.url_type in {
                    "official_job_detail",
                    "trusted_ats_job_detail",
                }:
                    if analyzed.company != company:
                        diag.dropped_unrelated += 1
                        continue
                    diag.detail_candidates += 1
                    hit.url = analyzed.url
                    hit.company = analyzed.company
                    hit.url_type = analyzed.url_type
                    hit.source_kind = analyzed.source_kind
                    hit.trusted_tenant = analyzed.tenant_host
                    hits.append(hit)
                elif analyzed.url_type in {
                    "official_job_list",
                    "trusted_ats_job_list",
                    "recruitment_landing_page",
                }:
                    if analyzed.company != company:
                        diag.dropped_unrelated += 1
                    else:
                        diag.dropped_list_or_landing += 1
                else:
                    diag.dropped_unrelated += 1

        for company, term, layer, domains in tasks:
            run(company, term, layer, domains)

        # Bounded fallback: exact -> broader keywords -> recruitment entry.
        # It only runs when the exact layer found no verified detail candidate,
        # and it still obeys the total query budget.
        if self._providers and any(provider.configured for provider in self._providers):
            for company in selected:
                diag = diagnostics[company]
                if diag.detail_candidates:
                    continue
                if executed_queries >= max_queries:
                    diag.reason = diag.reason or "查询预算已用尽，未执行回退搜索"
                    continue
                domains = search_domains_for([company])
                if not domains:
                    continue
                broad = f"{COMPANY_NAMES.get(company, company)} {' '.join(terms)} 招聘"
                run(company, broad, "broad", domains)
                if executed_queries >= max_queries or diag.detail_candidates:
                    continue
                entry = f"{COMPANY_NAMES.get(company, company)} 招聘 职位"
                run(company, entry, "entry", domains)

        if self._official is not None and "baidu" in selected:
            official_text = " ".join(terms)
            if job_type == "campus":
                official_text = f"{official_text} 校招"
            elif job_type == "internship":
                official_text = f"{official_text} 实习"
            official_hits, _official_cached, _official_called = self._call_provider(
                self._official,
                official_text,
                ["talent.baidu.com"],
                limit,
                warnings,
                user_id,
            )
            if official_hits:
                providers_used.append(self._official.name)
            for hit in official_hits:
                hit.url_type = "official_job_detail"
                hit.source_kind = "official"
            hits.extend(official_hits)

        licensed_configured = any(
            provider.configured and getattr(provider, "available", True)
            for provider in self._providers
        )
        configured = licensed_configured or self._official is not None
        if not licensed_configured:
            warnings.append(
                "Tavily 搜索 API 未配置；当前使用官方公开列表页或已有库，不代表全量实时结果"
            )

        filtered: list[SearchHit] = []
        tokens = [token for term in terms for token in term.split() if token]
        for hit in hits:
            diag = diagnostics.get(hit.company or "")
            try:
                official = classify_url(hit.url)
            except ValueError:
                if diag:
                    diag.dropped_invalid += 1
                continue
            hit.url = official.url
            hit.company = official.company
            hit.url_type = official.url_type
            hit.source_kind = official.source_kind
            hit.trusted_tenant = official.tenant_host
            haystack = f"{hit.title} {hit.snippet or ''} {hit.city or ''}".lower()
            if tokens and not any(token.lower() in haystack for token in tokens):
                if diag:
                    diag.dropped_filter += 1
                continue
            if city and hit.city and city.strip().removesuffix("市") not in hit.city:
                if diag:
                    diag.dropped_filter += 1
                continue
            if job_type and hit.job_type and job_type != hit.job_type:
                if diag:
                    diag.dropped_filter += 1
                continue
            if job_family and classify_job_family(hit.title, hit.snippet) != job_family:
                if diag:
                    diag.dropped_filter += 1
                continue
            if diag:
                diag.accepted += 1
            filtered.append(hit)

        fused = self._merge_hits(filtered)
        accepted_by_url: dict[str, int] = {}
        for hit in fused:
            accepted_by_url[hit.company or ""] = accepted_by_url.get(hit.company or "", 0) + 1
        for company, diag in diagnostics.items():
            diag.accepted = accepted_by_url.get(company, 0)
            diag.layers = sorted(layers_by_company[company])
            if diag.reason:
                continue
            if diag.provider_errors and diag.raw_results == 0:
                diag.reason = "Tavily 请求失败或超时"
            elif diag.queries == 0:
                diag.reason = "未执行查询：Provider 不可用或预算不足"
            elif diag.raw_results == 0:
                diag.reason = "Tavily 无搜索命中"
            elif diag.detail_candidates == 0:
                diag.reason = "仅发现招聘列表/入口，未发现职位详情"
            elif diag.accepted == 0:
                diag.reason = "职位详情被关键词、城市或岗位方向过滤"
            else:
                diag.reason = None

        warnings = list(dict.fromkeys(warnings))
        return SearchOutcome(
            hits=fused[:limit],
            providers_used=sorted(set(providers_used)),
            configured=configured,
            licensed_configured=licensed_configured,
            warnings=warnings,
            provider_queries=provider_queries,
            cached_queries=cached_queries,
            credits_estimated=credits_estimated,
            diagnostics=[diagnostics[company] for company in selected],
        )
