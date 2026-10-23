from __future__ import annotations

import json

import httpx
import pytest
from fakeredis import FakeRedis
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models.job_lead import SourceEvidence
from app.search.base import SearchError, SearchHit
from app.search.providers import TavilySearchProvider, build_search_provider
from app.search.service import SearchService
from app.services.job_lead_service import JobLeadService

BAIDU_URL = "https://talent.baidu.com/jobs/detail/INTERN/f8f8f186-2d4a-4b55-9f6c-34018f476896"


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "search_provider": "tavily",
        "tavily_api_key": "test-key",
        "search_timeout_seconds": 2,
        "search_cache_ttl_seconds": 0,
        "official_site_discovery_enabled": False,
        "search_rate_limit_per_minute": 30,
        "search_daily_budget_per_provider": 50,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tavily_provider_parses_results_and_sends_domain_scope() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Agent 实习",
                        "url": BAIDU_URL,
                        "content": "百度官方职位",
                        "published_date": "2026-10-20T12:00:00Z",
                    }
                ]
            },
            request=request,
        )

    provider = TavilySearchProvider(_settings(), client=_client(handler))
    hits = provider.search("Agent 实习", ["talent.baidu.com"], 10)

    assert captured["body"]["include_domains"] == ["talent.baidu.com"]
    assert captured["body"]["include_raw_content"] is False
    assert hits[0].provider == "tavily"
    assert hits[0].published_date is None
    assert hits[0].snippet == "百度官方职位"


def test_provider_builder_only_builds_configured_tavily() -> None:
    settings = _settings(tavily_api_key=None)
    provider = build_search_provider(settings)
    assert provider is not None
    assert provider.name == "tavily"
    assert provider.configured is False

    statuses = {
        item.name: item
        for item in SearchService(
            settings,
            redis_client=FakeRedis(decode_responses=True),
            providers=[provider],
            official_provider=None,
        ).provider_infos()
    }
    assert statuses["tavily"].enabled is True
    assert statuses["tavily"].configured is False
    assert statuses["tavily"].available is False
    assert "TAVILY_API_KEY" in (statuses["tavily"].reason or "")
    assert set(statuses) == {"tavily", "baidu_official_list"}


class _FakeProvider:
    available = True
    configured = True

    def __init__(self, name: str, hits: list[SearchHit] | None = None, fail: bool = False):
        self.name = name
        self._hits = hits or []
        self._fail = fail
        self.calls = 0

    def close(self) -> None:
        return None

    def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]:
        self.calls += 1
        if self._fail:
            raise SearchError("provider failed", retryable=True)
        return [
            SearchHit(
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                company=hit.company,
                rank=hit.rank,
                provider=self.name,
            )
            for hit in self._hits
        ]


def test_duplicate_urls_are_fused_and_keep_distinct_evidence(db_session) -> None:
    settings = _settings()
    tavily = _FakeProvider(
        "tavily",
        [SearchHit(title="Agent 实习", url=BAIDU_URL, snippet="来自 Tavily", rank=0)],
    )
    baidu = _FakeProvider(
        "baidu_official_list",
        [SearchHit(title="Agent 实习", url=BAIDU_URL, snippet="来自百度", rank=1)],
    )
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[tavily, baidu],
        official_provider=None,
    )
    outcome = service.search("Agent", company_keys=["baidu"])

    assert len(outcome.hits) == 1
    assert set(outcome.hits[0].providers) == {"tavily", "baidu_official_list"}
    assert set(outcome.providers_used) == {"tavily", "baidu_official_list"}

    lead = JobLeadService(db_session, settings).upsert_search_hit(outcome.hits[0])
    db_session.commit()
    evidence = list(
        db_session.scalars(select(SourceEvidence).where(SourceEvidence.lead_id == lead.id))
    )
    assert {row.evidence_ref for row in evidence} == {"tavily", "baidu_official_list"}


def test_provider_failure_falls_back_to_official_source() -> None:
    settings = _settings()

    class _FailingTavily(_FakeProvider):
        def __init__(self) -> None:
            super().__init__("tavily", fail=True)

    official = _FakeProvider(
        "baidu_official_list",
        [SearchHit(title="后端 实习", url=BAIDU_URL, snippet="官方列表")],
    )
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[_FailingTavily()],
        official_provider=official,
    )
    outcome = service.search("后端", company_keys=["baidu"])

    assert len(outcome.hits) == 1
    assert outcome.providers_used == ["baidu_official_list"]
    assert any("tavily" in warning for warning in outcome.warnings)


def test_daily_budget_stops_outbound_calls() -> None:
    settings = _settings(search_daily_budget_per_provider=1)
    provider = _FakeProvider(
        "tavily",
        [SearchHit(title="Agent 实习", url=BAIDU_URL, snippet="结果")],
    )
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[provider],
        official_provider=None,
    )

    first = service.search("Agent", company_keys=["baidu"])
    second = service.search("另一个查询", company_keys=["baidu"])

    assert len(first.hits) == 1
    assert second.hits == []
    assert provider.calls == 1
    assert any("每日请求预算" in warning for warning in second.warnings)


def test_unconfigured_tavily_is_never_called() -> None:
    settings = _settings(tavily_api_key=None)
    provider = build_search_provider(settings)
    assert provider is not None
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[provider],
        official_provider=None,
    )
    outcome = service.search("Agent", company_keys=["baidu"])

    assert outcome.hits == []
    assert outcome.licensed_configured is False
    assert any("未配置" in warning for warning in outcome.warnings)


def test_provider_evidence_is_not_duplicated_on_repeated_search(db_session) -> None:
    settings = _settings()
    provider = _FakeProvider("tavily", [SearchHit(title="Agent 实习", url=BAIDU_URL, snippet="T")])
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[provider],
        official_provider=None,
    )
    lead_service = JobLeadService(db_session, settings)
    for _ in range(2):
        outcome = service.search("Agent", company_keys=["baidu"])
        lead_service.upsert_search_hit(outcome.hits[0])
        db_session.commit()

    count = db_session.scalar(
        select(func.count(SourceEvidence.id)).where(SourceEvidence.evidence_ref == "tavily")
    )
    assert count == 1


def test_tavily_request_uses_configured_depth_and_no_official_date() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "小红书大模型实习",
                        "url": "https://job.xiaohongshu.com/campus/position/123",
                        "content": "职位详情",
                        "published_date": "2026-10-20T00:00:00Z",
                    }
                ]
            },
            request=request,
        )

    settings = _settings(
        tavily_search_depth="advanced",
        tavily_max_results=7,
    )
    provider = TavilySearchProvider(settings, client=_client(handler))
    hits = provider.search("大模型", ["job.xiaohongshu.com"], 20)

    assert captured["body"]["search_depth"] == "advanced"
    assert captured["body"]["max_results"] == 7
    assert captured["body"]["include_domains_mode"] == "restrict"
    assert captured["body"]["include_published_date"] is True
    assert hits[0].published_date is None


def test_multi_company_search_uses_one_query_per_company() -> None:
    settings = _settings()
    seen_domains: list[tuple[str, ...]] = []

    class _CapturingProvider(_FakeProvider):
        def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]:
            seen_domains.append(tuple(domains))
            return super().search(text, domains, limit)

    provider = _CapturingProvider(
        "tavily",
        [
            SearchHit(
                title="Agent 实习",
                url=BAIDU_URL,
                snippet="结果",
            )
        ],
    )
    original_search = provider.search

    def routed_search(text: str, domains: list[str], limit: int) -> list[SearchHit]:
        if "jobs.bytedance.com" in domains:
            seen_domains.append(tuple(domains))
            return [
                SearchHit(
                    title="Agent 实习",
                    url="https://jobs.bytedance.com/campus/position/123/detail",
                    snippet="结果",
                )
            ]
        return original_search(text, domains, limit)

    provider.search = routed_search  # type: ignore[method-assign]
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[provider],
        official_provider=None,
    )
    outcome = service.search(
        "Agent",
        company_keys=["baidu", "bytedance"],
    )

    assert len(seen_domains) == 2
    assert ("talent.baidu.com",) in seen_domains
    assert ("jobs.bytedance.com",) in seen_domains
    assert outcome.provider_queries == 2
    assert outcome.credits_estimated == 2


def test_official_source_catalog_is_verified_and_keeps_detail_scope_explicit() -> None:
    from app.search.source_catalog import official_sources

    sources = {source.company: source for source in official_sources()}
    assert len(sources) == 19
    assert sources["xiaohongshu"].priority == "P0"
    assert sources["minimax"].priority == "P1"
    assert all(source.http_status == 200 for source in sources.values())
    assert sources["baidu"].detail_verification == "baidu_public_detail"
    assert sources["xiaohongshu"].detail_verification == "manual_link_only"
    assert sources["minimax"].trusted_tenants[0].host == "vrfi1sk8a0.jobs.feishu.cn"
    assert sources["kimi"].trusted_tenants[0].path_prefix == "/apply/moonshot/148506"
    assert sources["ctrip"].trusted_tenants[0].path_prefix == "/campus-recruitment/trip/117988"


def test_ats_tenants_are_path_scoped_and_not_global() -> None:
    from app.search.domains import analyze_url, classify_url

    minimax = analyze_url(
        "https://vrfi1sk8a0.jobs.feishu.cn/379481/position/7674980747073095986/detail"
    )
    assert minimax.company == "minimax"
    assert minimax.url_type == "trusted_ats_job_detail"
    assert minimax.source_kind == "trusted_ats"

    moka = analyze_url(
        "https://app.mokahr.com/apply/moonshot/148506#/job/43c794f9-901c-430e-b1fb-6f5f96c29492"
    )
    assert moka.company == "kimi"
    assert moka.url_type == "trusted_ats_job_detail"
    assert moka.url.endswith("#/job/43c794f9-901c-430e-b1fb-6f5f96c29492")

    other_tenant = analyze_url(
        "https://app.mokahr.com/campus-recruitment/zphz/148984#/job/43c794f9-901c-430e-b1fb-6f5f96c29492"
    )
    assert other_tenant.url_type == "unrelated_page"
    assert other_tenant.source_kind == "untrusted"

    other_feishu = analyze_url("https://other.jobs.feishu.cn/379481/position/1/detail")
    assert other_feishu.url_type == "unrelated_page"

    with pytest.raises(ValueError):
        classify_url("https://app.mokahr.com/campus-recruitment/zphz/148984#/job/43c794f9")
    with pytest.raises(ValueError):
        classify_url("https://vrfi1sk8a0.jobs.feishu.cn/379481/")


def test_ats_tenant_is_used_for_search_and_accepted_as_detail() -> None:
    settings = _settings()
    seen_domains: list[tuple[str, ...]] = []
    ats_url = "https://vrfi1sk8a0.jobs.feishu.cn/379481/position/7674980747073095986/detail"

    class _AtsProvider(_FakeProvider):
        def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]:
            seen_domains.append(tuple(domains))
            return [
                SearchHit(
                    title="MiniMax 大模型算法实习",
                    url=ats_url,
                    snippet="官方飞书招聘租户",
                )
            ]

    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[_AtsProvider("tavily")],
        official_provider=None,
    )
    outcome = service.search("大模型 实习", company_keys=["minimax"])

    assert "vrfi1sk8a0.jobs.feishu.cn" in seen_domains[0]
    assert len(outcome.hits) == 1
    assert outcome.hits[0].source_kind == "trusted_ats"
    assert outcome.hits[0].url_type == "trusted_ats_job_detail"
    assert outcome.diagnostics[0].accepted == 1


def test_untrusted_ats_tenant_is_not_attributed_to_company() -> None:
    settings = _settings()
    wrong_ats = "https://other.jobs.feishu.cn/379481/position/7674980747073095986/detail"

    class _WrongAtsProvider(_FakeProvider):
        def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]:
            return [SearchHit(title="MiniMax 大模型实习", url=wrong_ats, snippet="其他租户")]

    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[_WrongAtsProvider("tavily")],
        official_provider=None,
    )
    outcome = service.search("大模型", company_keys=["minimax"])

    assert outcome.hits == []
    assert outcome.diagnostics[0].dropped_unrelated >= 1
    assert outcome.diagnostics[0].reason is not None


def test_fallback_broad_query_runs_after_listing_only_result() -> None:
    settings = _settings()
    calls: list[str] = []
    detail_url = "https://jobs.bilibili.com/campus/positions/28825"

    class _FallbackProvider(_FakeProvider):
        def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]:
            calls.append(text)
            if "招聘" in text and "B站" not in text:
                return [
                    SearchHit(
                        title="哔哩哔哩 推荐算法 实习生",
                        url=detail_url,
                        snippet="职位详情",
                    )
                ]
            return [
                SearchHit(
                    title="哔哩哔哩招聘",
                    url="https://jobs.bilibili.com/campus/positions?type=0",
                    snippet="职位列表",
                )
            ]

    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        providers=[_FallbackProvider("tavily")],
        official_provider=None,
    )
    outcome = service.search("推荐算法 实习生", company_keys=["bilibili"])

    assert len(calls) >= 2
    assert outcome.hits
    assert outcome.hits[0].search_layer in {"broad", "entry"}
    assert outcome.diagnostics[0].accepted == 1
    assert "exact" in outcome.diagnostics[0].layers
