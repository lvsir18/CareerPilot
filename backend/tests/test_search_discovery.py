from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
from fakeredis import FakeRedis
from sqlalchemy import select

from app.core.config import Settings
from app.db.models.job_lead import JobLead
from app.search.base import SearchHit, SearchOutcome
from app.search.domains import canonical_official_url
from app.search.providers import BaiduOfficialListProvider, TavilySearchProvider
from app.search.service import SearchService
from app.services.job_discovery_service import JobDiscoveryService

LIST_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "baidu_list.html"
BAIDU_URL = "https://talent.baidu.com/jobs/detail/INTERN/f8f8f186-2d4a-4b55-9f6c-34018f476896"


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "search_provider": "tavily",
        "tavily_api_key": "test-key",
        "official_site_discovery_enabled": False,
        "search_rate_limit_per_minute": 30,
    }
    values.update(overrides)
    return Settings(**values)


def test_official_url_allowlist_rejects_spoofed_hosts_and_lists() -> None:
    assert canonical_official_url(BAIDU_URL).company == "baidu"
    with pytest.raises(ValueError):
        canonical_official_url("https://jobs.bytedance.com.evil.test/campus/position/1/detail")
    with pytest.raises(ValueError):
        canonical_official_url("http://talent.baidu.com/jobs/detail/INTERN/x")
    with pytest.raises(ValueError):
        canonical_official_url("https://talent.baidu.com/jobs/list?recruitType=INTERN")


def test_tavily_provider_filters_official_hosts_and_dedupes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Agent 实习", "url": BAIDU_URL, "content": "北京"},
                    {"title": "Agent 实习重复", "url": BAIDU_URL, "content": "重复"},
                    {
                        "title": "伪造岗位",
                        "url": "https://talent.baidu.com.evil.test/jobs/detail/INTERN/x",
                    },
                    {
                        "title": "Agent 字节岗位",
                        "url": "https://jobs.bytedance.com/campus/position/123/detail",
                    },
                ]
            },
            request=request,
        )

    settings = _settings()
    provider = TavilySearchProvider(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        provider=provider,
        official_provider=None,
    )

    outcome = service.search("Agent", company_keys=["baidu", "bytedance"], limit=10)

    assert outcome.licensed_configured is True
    assert [hit.url for hit in outcome.hits] == [
        BAIDU_URL,
        "https://jobs.bytedance.com/campus/position/123/detail",
    ]
    assert outcome.providers_used == ["tavily"]


def test_unconfigured_search_returns_warning_not_fake_hits() -> None:
    settings = _settings(
        search_provider="none",
        tavily_api_key=None,
        official_site_discovery_enabled=False,
    )
    outcome = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        official_provider=None,
    ).search("Agent", company_keys=["baidu"])

    assert outcome.configured is False
    assert outcome.licensed_configured is False
    assert outcome.hits == []
    assert any("未配置" in warning for warning in outcome.warnings)


def test_search_cache_avoids_duplicate_provider_calls() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            200,
            json={"results": [{"title": "Agent", "url": BAIDU_URL, "content": "北京"}]},
            request=request,
        )

    settings = _settings()
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        provider=TavilySearchProvider(
            settings, client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
        official_provider=None,
    )

    assert service.search("Agent", company_keys=["baidu"]).hits
    assert service.search("Agent", company_keys=["baidu"]).hits
    assert calls["count"] == 1


def test_search_rate_limit_stops_extra_calls() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"results": []}, request=request)

    settings = _settings(search_rate_limit_per_minute=1, search_cache_ttl_seconds=0)
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        provider=TavilySearchProvider(
            settings, client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
        official_provider=None,
    )

    assert service.search("first", company_keys=["baidu"]).hits == []
    second = service.search("second", company_keys=["baidu"])

    assert second.hits == []
    assert any("每分钟最多" in warning for warning in second.warnings)
    assert calls["count"] == 1


class _FakeBaiduListClient:
    def get_text(self, url: str) -> str:
        return LIST_FIXTURE.read_text(encoding="utf-8")

    def close(self) -> None:
        return None


def test_baidu_official_list_provider_parses_real_shape() -> None:
    settings = _settings(official_site_discovery_enabled=True)
    provider = BaiduOfficialListProvider(settings, client=_FakeBaiduListClient())  # type: ignore[arg-type]

    hits = provider.search("实习", ["talent.baidu.com"], 10)

    assert len(hits) == 2
    assert hits[0].url == BAIDU_URL
    assert hits[0].published_date == date(2026, 10, 20)
    assert hits[0].city == "北京"
    assert hits[0].job_type == "internship"


class _FakeSearch:
    def search(self, text: str, **kwargs) -> SearchOutcome:
        return SearchOutcome(
            hits=[
                SearchHit(
                    title="Agent策略工程师",
                    url=BAIDU_URL,
                    snippet="日常实习项目",
                    company="baidu",
                    city="北京",
                    job_type="internship",
                    published_date=date(2026, 10, 20),
                )
            ],
            providers_used=["test_provider"],
            configured=True,
            licensed_configured=True,
        )


def test_discovery_persists_search_hit_as_candidate_lead(db_session, settings: Settings) -> None:
    service = JobDiscoveryService(
        db_session,
        settings,
        search_service=_FakeSearch(),  # type: ignore[arg-type]
    )

    result = service.discover(user_id=__import__("uuid").uuid4(), query="Agent", company="baidu")

    assert result.total_leads == 1
    lead = db_session.scalar(select(JobLead))
    assert lead is not None
    assert lead.verification_status == "search_snippet_only"
    assert lead.source_method == "search_discovery"
    assert lead.job_id is None
    assert result.leads[0].official_url == BAIDU_URL
    assert result.search.licensed_configured is True


def test_provider_registry_only_exposes_tavily_and_baidu() -> None:
    settings = _settings(
        search_provider="none",
        tavily_api_key=None,
        official_site_discovery_enabled=False,
    )
    service = SearchService(
        settings,
        redis_client=FakeRedis(decode_responses=True),
        provider=None,
        official_provider=None,
    )
    statuses = {item.name: item for item in service.provider_infos()}

    assert set(statuses) == {"tavily", "baidu_official_list"}
    assert statuses["tavily"].role == "primary"
    assert statuses["tavily"].available is False
    assert statuses["tavily"].configured is False
    assert statuses["baidu_official_list"].role == "fallback"


def test_job_family_classifier_is_explainable_and_falls_back() -> None:
    from app.search.taxonomy import classify_job_family

    # Families were split: 算法/数据, 后端/基础架构, 前端/客户端, LLM/Agent.
    assert classify_job_family("Agent 策略工程师") == "agent"
    assert classify_job_family("大模型算法工程师") == "llm"
    assert classify_job_family("推荐算法工程师") == "algorithm"
    assert classify_job_family("数据分析师") == "data"
    assert classify_job_family("Java 后端开发") == "backend"
    assert classify_job_family("基础架构工程师") == "infra"
    assert classify_job_family("前端工程师") == "frontend"
    assert classify_job_family("Android 客户端开发") == "client"
    assert classify_job_family("测试开发工程师") == "test"
    assert classify_job_family("安全工程师") == "security"
    assert classify_job_family("行政专员") == "other"


def test_legacy_coarse_filters_still_match_the_split_families() -> None:
    from app.search.taxonomy import is_known_family, job_family_matches

    assert is_known_family("algorithm")
    assert is_known_family("algorithm_data")
    assert not is_known_family("not-a-family")

    assert job_family_matches("algorithm", "algorithm_data")
    assert job_family_matches("data", "algorithm_data")
    assert not job_family_matches("backend", "algorithm_data")
    assert job_family_matches("llm", "llm_agent")
    assert job_family_matches("agent", "llm_agent")
    # A fine-grained filter no longer drags its old group along.
    assert job_family_matches("infra", "backend") is False


class _MultiCompanySearch:
    def search(self, text: str, **kwargs) -> SearchOutcome:
        return SearchOutcome(
            hits=[
                SearchHit(
                    title="Agent 策略工程师",
                    url=BAIDU_URL,
                    snippet="日常实习项目",
                    company="baidu",
                    city="北京",
                    job_type="internship",
                ),
                SearchHit(
                    title="Agent 算法工程师",
                    url="https://jobs.bytedance.com/campus/position/123/detail",
                    snippet="校园招聘",
                    company="bytedance",
                    city="北京",
                    job_type="campus",
                ),
            ],
            providers_used=["test"],
            configured=True,
            licensed_configured=True,
        )


def test_multi_company_family_filter_and_pagination(db_session, settings: Settings) -> None:
    from uuid import uuid4

    service = JobDiscoveryService(
        db_session,
        settings,
        search_service=_MultiCompanySearch(),  # type: ignore[arg-type]
    )
    first = service.discover(
        user_id=uuid4(),
        query="Agent",
        companies=["baidu", "bytedance"],
        job_family="llm_agent",
        page=1,
        page_size=1,
    )

    assert first.companies == ["baidu", "bytedance"]
    assert first.total_leads == 2
    assert first.total_pages == 2
    assert len(first.leads) == 1
    # The legacy "llm_agent" filter accepts the new split families.
    assert first.leads[0].job_family in {"llm", "agent"}
    assert len(first.search.provider_results) == 2

    second = service.discover(
        user_id=uuid4(),
        query="Agent",
        companies=["baidu", "bytedance"],
        job_family="llm_agent",
        page=2,
        page_size=1,
    )
    assert len(second.leads) == 1
    assert second.leads[0].id != first.leads[0].id


def test_m2r3_fixed_query_set_has_at_least_20_queries() -> None:
    import json

    queries = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "m2r3_queries.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(queries) >= 20
    assert len({item["id"] for item in queries}) == len(queries)
    assert {item["companies"][0] for item in queries} >= {
        "baidu",
        "bytedance",
        "tencent",
        "alibaba",
        "meituan",
    }


class _CountingSearch:
    """Counts live-search calls so the skip path is observable."""

    def __init__(self) -> None:
        self.calls = 0

    def search(self, text, **kwargs) -> SearchOutcome:
        self.calls += 1
        return SearchOutcome(hits=[], providers_used=[], configured=True, licensed_configured=False)

    def provider_infos(self) -> list:
        return []

    def close(self) -> None:
        return None


def test_multi_keyword_query_matches_any_term(db_session, settings: Settings) -> None:
    """Agent tools join keywords ("大模型 LLM Agent"); a verbatim match is 0 rows."""
    from tests.factories import create_job

    create_job(
        db_session,
        title="大模型算法实习生",
        city="北京",
        job_type="internship",
        description="负责大模型训练与评测。",
        source_job_id="kw-1",
    )
    create_job(
        db_session,
        title="LLM 应用实习生",
        city="北京",
        job_type="internship",
        description="负责推理服务。",
        source_job_id="kw-2",
    )
    create_job(
        db_session,
        title="后端开发实习生",
        city="北京",
        job_type="internship",
        description="负责服务端接口。",
        source_job_id="kw-3",
    )

    service = JobDiscoveryService(db_session, settings, search_service=_CountingSearch())
    result = service.discover(
        user_id=__import__("uuid").uuid4(),
        query="大模型 LLM Agent",
        city="北京",
        job_type="internship",
        prefer_local=True,
    )

    titles = {job.title for job in result.jobs}
    assert {"大模型算法实习生", "LLM 应用实习生"} <= titles
    assert "后端开发实习生" not in titles


def test_prefer_local_skips_live_search_when_library_has_hits(
    db_session, settings: Settings
) -> None:
    from tests.factories import create_job

    create_job(
        db_session,
        title="大模型算法实习生",
        city="北京",
        job_type="internship",
        description="负责大模型训练。",
        source_job_id="pref-1",
    )
    search = _CountingSearch()
    service = JobDiscoveryService(db_session, settings, search_service=search)

    result = service.discover(
        user_id=__import__("uuid").uuid4(),
        query="大模型",
        city="北京",
        job_type="internship",
        prefer_local=True,
    )

    assert search.calls == 0
    assert result.total_jobs >= 1
    assert any("跳过实时检索" in warning for warning in result.search.warnings)


def test_prefer_local_falls_back_to_live_search_when_library_is_empty(
    db_session, settings: Settings
) -> None:
    search = _CountingSearch()
    service = JobDiscoveryService(db_session, settings, search_service=search)

    service.discover(
        user_id=__import__("uuid").uuid4(),
        query="大模型",
        city="北京",
        job_type="internship",
        prefer_local=True,
    )

    assert search.calls == 1


def test_unknown_company_is_skipped_with_a_warning(db_session, settings: Settings) -> None:
    """One unrecognised company name must not fail the whole search."""
    from tests.factories import create_job

    create_job(
        db_session,
        title="大模型算法实习生",
        company="字节跳动",
        city="杭州",
        job_type="internship",
        description="负责大模型训练。",
        source_job_id="unknown-company-1",
    )
    service = JobDiscoveryService(db_session, settings, search_service=_CountingSearch())

    result = service.discover(
        user_id=__import__("uuid").uuid4(),
        query="大模型",
        city="杭州",
        job_type="internship",
        companies=["bytedance", "阿里巴巴达摩院"],
        prefer_local=True,
    )

    assert any("已忽略无法识别的企业" in warning for warning in result.search.warnings)
    assert result.total_jobs == 1
