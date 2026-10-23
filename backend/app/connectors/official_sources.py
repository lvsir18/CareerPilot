"""Per-company official source registry.

Two ingest routes exist, chosen per company by what the site actually offers:

1. ``api`` — the site exposes an unauthenticated JSON API (Tencent). Fastest and
   most stable; implemented in :mod:`app.connectors.tencent_campus`.
2. ``rendered`` — the site is a SPA whose XHRs are signed by front-end code
   (ByteDance ``_signature``, Xiaohongshu ``x-s``). We load the official search
   page in a real browser and read the JSON it receives
   (:mod:`app.connectors.rendered`).

Only internship/campus routes are configured: social recruiting is out of scope
by product decision.
"""

from __future__ import annotations

from app.connectors.rendered import RenderedSourceSpec

# Companies with a plain JSON API.
API_SOURCES: dict[str, str] = {
    "tencent": "tencent_campus",
}

# Companies handled by rendering their official public search page.
# ``search_input`` matters: these SPAs ignore ``?keyword=`` and only query when
# the keyword is typed into their own search box.
RENDERED_SOURCES: dict[str, RenderedSourceSpec] = {
    "bytedance": RenderedSourceSpec(
        source_type="bytedance_campus_rendered",
        company="字节跳动",
        search_url="https://jobs.bytedance.com/campus/position?keywords={keyword}",
        detail_url="https://jobs.bytedance.com/campus/position/{id}/detail",
        job_type="campus",
        recruitment_program="校园招聘",
        wait_ms=9000,
        # ByteDance honours ?keywords= on load, so no box handling is needed.
        note="签名参数 _signature 由前端生成，只能由浏览器发起请求",
    ),
    "xiaohongshu": RenderedSourceSpec(
        source_type="xiaohongshu_campus_rendered",
        company="小红书",
        search_url="https://job.xiaohongshu.com/campus/position",
        detail_url="https://job.xiaohongshu.com/campus/position/{id}",
        job_type="campus",
        recruitment_program="校园招聘",
        wait_ms=9000,
        search_input="input[placeholder*='搜索']",
        note="x-s / x-s-common 由前端生成；列表接口固定 recruitType=campus",
    ),
    "bilibili": RenderedSourceSpec(
        source_type="bilibili_campus_rendered",
        company="哔哩哔哩",
        search_url="https://jobs.bilibili.com/campus/positions",
        detail_url="https://jobs.bilibili.com/campus/positions/{id}",
        job_type="campus",
        recruitment_program="校园招聘",
        wait_ms=9000,
        search_input="input[placeholder*='搜索']",
        note="列表接口要求页面下发的 ajSessionId，只能由浏览器发起",
    ),
    "meituan": RenderedSourceSpec(
        source_type="meituan_campus_rendered",
        company="美团",
        search_url="https://zhaopin.meituan.com/web/campus",
        detail_url="https://zhaopin.meituan.com/web/position/detail?jobUnionId={id}&jobShareType=1",
        job_type="campus",
        recruitment_program="校园招聘",
        wait_ms=10000,
        search_input="input[placeholder*='关键词']",
        # 社招与校招共用同一列表接口，只有「应届校招」页签会把 jobType 收窄到校招。
        pre_click_text="应届校招",
        note="社招/校招共用接口，需先切到「应届校招」页签",
    ),
}

COMPANY_LABELS: dict[str, str] = {
    "tencent": "腾讯",
    "bytedance": "字节跳动",
    "xiaohongshu": "小红书",
    "bilibili": "哔哩哔哩",
    "meituan": "美团",
}


def supports_official(company: str) -> bool:
    return company in API_SOURCES or company in RENDERED_SOURCES


def official_company_keys() -> list[str]:
    return sorted(set(API_SOURCES) | set(RENDERED_SOURCES))
