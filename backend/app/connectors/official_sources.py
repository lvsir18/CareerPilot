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
    # JD exposes an unauthenticated POST endpoint that already carries the JD.
    "jd": "jd_campus",
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
    "minimax": RenderedSourceSpec(
        source_type="minimax_campus_rendered",
        company="MiniMax",
        search_url="https://vrfi1sk8a0.jobs.feishu.cn/379481/?keywords={keyword}",
        detail_url="https://vrfi1sk8a0.jobs.feishu.cn/379481/position/{id}/detail",
        job_type="campus",
        recruitment_program="校园招聘",
        wait_ms=14000,
        note="飞书招聘托管：接口带 _signature，只能浏览器渲染；?keywords= 生效",
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

# Every company the discovery filter offers. Only the subset registered above can
# be searched by direct connection; the rest stay listed so the UI can say why.
COMPANY_LABELS: dict[str, str] = {
    "bytedance": "字节跳动",
    "tencent": "腾讯",
    "alibaba": "阿里巴巴",
    "baidu": "百度",
    "meituan": "美团",
    "xiaohongshu": "小红书",
    "bilibili": "哔哩哔哩",
    "dewu": "得物",
    "deepseek": "DeepSeek",
    "360": "360",
    "xiaomi": "小米",
    "minimax": "MiniMax",
    "jd": "京东",
    "kimi": "月之暗面 Kimi",
    "ctrip": "携程",
    "kuaishou": "快手",
    "netease": "网易",
    "huawei": "华为",
    "pdd": "拼多多",
}

# Why a company is *not* wired yet. Probed on 2026-10-24; each note explains what
# actually happened, so the UI can point at the workaround instead of failing.
UNSUPPORTED_NOTES: dict[str, str] = {
    "alibaba": "校园招聘站为前端渲染，列表接口需站内签名，抓到的是非岗位模块",
    "baidu": "招聘站点会跳转到统一入口页，没有稳定的公开职位列表",
    "dewu": "校招页可打开且有搜索框，但检索请求未返回可解析的职位 JSON",
    "deepseek": "官网未提供公开职位列表页",
    "360": "校招页可打开，职位列表经接口返回且格式不稳定",
    "xiaomi": "校招页返回的是招聘计划卡片，不是职位列表",
    "kimi": "招聘页未提供可公开检索的职位列表",
    "ctrip": "校招页返回招聘动态/项目介绍，不是职位列表",
    "kuaishou": "职位列表需站内交互后加载，未捕获到可解析数据",
    "netease": "校招页首页是分类入口，职位列表需进一步下钻",
    "huawei": "有搜索框，但检索结果未以可解析 JSON 返回",
    "pdd": "校招页职位列表接口未公开，未捕获到可解析数据",
}


# Where to send the user when a company is not wired for direct search. A
# ``{keyword}`` placeholder is filled in when the site supports query params.
SEARCH_PAGES: dict[str, str] = {
    "alibaba": "https://campus-talent.alibaba.com/campus/index",
    "baidu": "https://talent.baidu.com",
    "dewu": "https://campus.dewu.com/",
    "deepseek": "https://www.deepseek.com/",
    "360": "https://campus.360.cn/home",
    "xiaomi": "https://hr.xiaomi.com/website/campus.html",
    "kimi": "https://www.moonshot.cn/",
    "ctrip": "https://job.ctrip.com/#/campus",
    "kuaishou": "https://campus.kuaishou.cn/recruit/campus/e/#/campus/index/",
    "netease": "https://campus.163.com/app/index",
    "huawei": "https://career.huawei.com/cn/campus-recruitment",
    "pdd": "https://careers.pddglobalhr.com/campus",
}


def supports_official(company: str) -> bool:
    return company in API_SOURCES or company in RENDERED_SOURCES


def official_company_keys() -> list[str]:
    """Companies that can actually be searched by direct connection."""
    return sorted(set(API_SOURCES) | set(RENDERED_SOURCES))


def official_catalog() -> list[dict[str, object]]:
    """All filterable companies, with an explicit supported/unsupported flag."""
    items: list[dict[str, object]] = []
    for key, label in COMPANY_LABELS.items():
        if key in API_SOURCES:
            items.append({"key": key, "label": label, "supported": True, "mode": "api", "note": ""})
        elif key in RENDERED_SOURCES:
            items.append(
                {
                    "key": key,
                    "label": label,
                    "supported": True,
                    "mode": "rendered",
                    "note": RENDERED_SOURCES[key].note,
                    "search_page": SEARCH_PAGES.get(key, ""),
                }
            )
        else:
            items.append(
                {
                    "key": key,
                    "label": label,
                    "supported": False,
                    "mode": "none",
                    "note": UNSUPPORTED_NOTES.get(key, "暂未适配官方直连"),
                    "search_page": SEARCH_PAGES.get(key, ""),
                }
            )
    return items
