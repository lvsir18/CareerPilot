"""Verified official recruiting sources and narrowly-scoped ATS tenants.

A trusted ATS tenant is an explicit (host, path prefix, company) relationship
backed by an official recruiting page. The ATS host itself is never treated as
a company-wide source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.search.domains import (
    COMPANY_DOMAINS,
    COMPANY_NAMES,
    TRUSTED_TENANTS,
    TrustedTenant,
    search_domains_for,
)


@dataclass(frozen=True, slots=True)
class OfficialSource:
    company: str
    name: str
    domains: tuple[str, ...]
    priority: str
    http_status: int
    final_url: str
    verified_at: date
    detail_verification: str
    note: str
    official_entrypoints: tuple[str, ...]
    trusted_tenants: tuple[TrustedTenant, ...]
    search_domains: tuple[str, ...]
    job_url_patterns: tuple[str, ...]
    verification_status: str
    access_policy: str


_VERIFIED_AT = date(2026, 10, 21)

_FINAL_URLS = {
    "bytedance": "https://jobs.bytedance.com/",
    "tencent": "https://join.qq.com/",
    "alibaba": "https://talent.alibaba.com/",
    "baidu": "https://talent.baidu.com/jobs/social",
    "meituan": "https://career.meituan.com/web/home",
    "xiaohongshu": "https://job.xiaohongshu.com/",
    "bilibili": "https://jobs.bilibili.com/",
    "dewu": "https://careers.dewu.com/",
    "deepseek": "https://talent.deepseek.com/",
    "360": "https://hr.360.cn/hr/",
    "xiaomi": "https://hr.xiaomi.com/",
    "minimax": "https://minimax.cn/careers",
    "jd": "https://campus.jd.com/",
    "kimi": "https://careers.kimi.com/campus",
    "ctrip": "https://careers.ctrip.com/",
    "kuaishou": "https://campus.kuaishou.cn/",
    "netease": "https://campus.163.com/",
    "huawei": "https://career.huawei.com/cn",
    "pdd": "https://careers.pddglobalhr.com/campus/",
}

_NAMES = {
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

_PRIORITY = {
    key: (
        "P0"
        if key
        in {
            "bytedance",
            "tencent",
            "alibaba",
            "baidu",
            "meituan",
            "xiaohongshu",
            "bilibili",
            "dewu",
            "deepseek",
            "360",
        }
        else "P1"
    )
    for key in COMPANY_DOMAINS
}

_PATTERNS = {
    "bytedance": ("/campus/position/*/detail", "/experienced/position/*/detail"),
    "tencent": ("/post.html?postId=*",),
    "alibaba": ("/off-campus/position-detail?positionId=*",),
    "baidu": ("/jobs/detail/*/*",),
    "meituan": ("/web/position/detail/*",),
    "xiaohongshu": ("/campus/position/*",),
    "bilibili": ("/campus/positions/*",),
    "dewu": ("/position/*",),
    "deepseek": ("/job/*", "/jobs/*"),
    "360": ("/hr/position/*",),
    "xiaomi": ("/campus/view/*", "/website/opportunities.html"),
    "minimax": (
        "/379481/position/*/detail",
        "/379481/m/position/*/detail",
    ),
    "jd": ("/campus/position/*", "/web/position/*"),
    "kimi": ("/apply/moonshot/148506#/job/*",),
    "ctrip": ("/campus-recruitment/trip/117988#/job/*",),
    "kuaishou": ("/job/*", "/campus/position/*"),
    "netease": ("/app/job/position?id=*", "/app/detail/index?id=*"),
    "huawei": ("/job/*", "/campus/*"),
    "pdd": ("/campus/position/*", "/position/*"),
}


def _tenants_for(company: str) -> tuple[TrustedTenant, ...]:
    return tuple(tenant for tenant in TRUSTED_TENANTS if tenant.company == company)


def official_sources() -> list[OfficialSource]:
    rows: list[OfficialSource] = []
    for company, domains in COMPANY_DOMAINS.items():
        tenants = _tenants_for(company)
        entrypoints = tuple(
            dict.fromkeys([_FINAL_URLS[company], *(tenant.entry_url for tenant in tenants)])
        )
        rows.append(
            OfficialSource(
                company=company,
                name=_NAMES.get(company, COMPANY_NAMES.get(company, company)),
                domains=domains,
                priority=_PRIORITY[company],
                http_status=200,
                final_url=_FINAL_URLS[company],
                verified_at=_VERIFIED_AT,
                detail_verification=(
                    "baidu_public_detail"
                    if company == "baidu"
                    else "trusted_ats_link_only"
                    if tenants
                    else "manual_link_only"
                ),
                note=(
                    "官方详情页自动核验"
                    if company == "baidu"
                    else "可信 ATS 详情链接，完整 JD 仍需人工/官方授权访问"
                    if tenants
                    else "官网域名可达；搜索结果仍为 JobLead，详情需人工打开"
                ),
                official_entrypoints=entrypoints,
                trusted_tenants=tenants,
                search_domains=tuple(search_domains_for([company])),
                job_url_patterns=_PATTERNS.get(company, ()),
                verification_status="verified_ats" if tenants else "verified_domain",
                access_policy="public_link_discovery_only",
            )
        )
    return rows
