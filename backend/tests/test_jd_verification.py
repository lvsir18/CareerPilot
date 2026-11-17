from __future__ import annotations

import json

import httpx
from fakeredis import FakeRedis

from app.core.config import Settings
from app.services.jd_parser import parse_jd
from app.services.tavily_extract import TavilyExtractService

URL = "https://vrfi1sk8a0.jobs.feishu.cn/379481/position/7655253685333936403/detail"
JD = """# 大模型算法实习生

工作地点：北京

职位描述
1. 参与大模型 Agent 的算法研发、评测和线上效果优化。
2. 与产品、工程团队协作推进算法落地和迭代。

任职要求
1. 熟悉 Python、PyTorch 和大模型基础。
2. 有 RAG 或 Agent 项目经验优先。
3. 具备良好的工程能力、沟通能力和团队协作意识，能够持续跟进业务与模型的迭代。
4. 对招聘流程、候选人体验和内容质量有责任心，能在快节奏环境中稳定交付。
"""


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "search_provider": "none",
        "tavily_api_key": "tvly-test",
        "tavily_extract_depth": "basic",
        "tavily_extract_timeout_seconds": 2,
        "tavily_extract_cache_ttl_seconds": 600,
        "tavily_extract_daily_budget": 10,
        "official_site_discovery_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tavily_extract_success_and_cache() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        captured = json.loads(request.content)
        assert captured["urls"] == [URL]
        assert captured["extract_depth"] == "basic"
        return httpx.Response(
            200,
            json={"results": [{"url": URL, "raw_content": JD}], "failed_results": []},
            request=request,
        )

    service = TavilyExtractService(
        _settings(),
        redis_client=FakeRedis(decode_responses=True),
        client=_client(handler),
    )
    first = service.extract(URL)
    second = service.extract(URL)

    assert first.success is True
    assert first.content == JD
    assert first.cached is False
    assert second.cached is True
    assert calls["count"] == 1


def test_tavily_extract_failed_results_keeps_failure_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [],
                "failed_results": [{"url": URL, "error": "Failed to fetch url"}],
            },
            request=request,
        )

    service = TavilyExtractService(
        _settings(),
        redis_client=FakeRedis(decode_responses=True),
        client=_client(handler),
    )
    result = service.extract(URL)

    assert result.success is False
    assert "Failed to fetch" in (result.error or "")


def test_tavily_extract_requires_key_and_rejects_untrusted_url() -> None:
    service = TavilyExtractService(
        _settings(tavily_api_key=None),
        redis_client=FakeRedis(decode_responses=True),
        client=_client(lambda request: httpx.Response(200, json={}, request=request)),
    )
    assert service.extract(URL).success is False
    assert "TAVILY_API_KEY" in (service.extract(URL).error or "")
    assert service.extract("https://other.jobs.feishu.cn/379481/position/1/detail").success is False


def test_jd_parser_marks_complete_and_incomplete_pages() -> None:
    complete = parse_jd(
        JD, company_key="minimax", official_url=URL, fallback_title="大模型算法实习生"
    )
    assert complete.is_complete is True
    assert complete.title == "大模型算法实习生"
    assert complete.location == "北京"
    assert complete.job_type == "internship"
    assert complete.official_job_id == "7655253685333936403"
    assert complete.responsibilities
    assert complete.requirements
    assert complete.field_sources["company"] == "config"

    incomplete = parse_jd(
        "首页 登录 招聘",
        company_key="minimax",
        official_url=URL,
        fallback_title="大模型算法实习生",
    )
    assert incomplete.is_complete is False
    assert "提取正文过短" in incomplete.incomplete_reasons


def test_jd_parser_rejects_closed_job_and_reads_explicit_date() -> None:
    text = """# 韩语游戏运营实习生

上海 实习 游戏类 2026-08-13 发布

职位描述
工作职责：1. 负责社区运营。2. 跟进内容审核。

任职要求
1. 韩语流利。2. 有游戏行业经验。

职位已下架
"""
    parsed = parse_jd(
        text,
        company_key="bilibili",
        official_url="https://jobs.bilibili.com/campus/positions/29952",
        fallback_title="韩语游戏运营实习生",
    )
    assert parsed.is_complete is False
    assert parsed.is_open is False
    assert parsed.published_date is not None
    assert parsed.published_date.isoformat() == "2026-08-13"
    assert any("已下架" in reason for reason in parsed.incomplete_reasons)


def test_jd_parser_handles_inline_markdown_sections() -> None:
    text = """韩语游戏运营实习生

职位描述
**工作职责:** 1.代理商沟通；2.内容审核。 **工作要求:** 1.韩语流利；2.热爱游戏。
"""
    parsed = parse_jd(
        text,
        company_key="bilibili",
        official_url="https://jobs.bilibili.com/campus/positions/29952",
        fallback_title="韩语游戏运营实习生",
    )
    assert parsed.responsibilities
    assert parsed.requirements
    assert "韩语流利" in " ".join(parsed.requirements)
