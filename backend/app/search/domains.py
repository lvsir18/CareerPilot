"""Official recruiting hosts, trusted ATS tenants and URL classification.

A third-party ATS host is never trusted globally. A URL is attributed to a
company only when the host and the tenant path prefix both match an explicitly
verified tenant configuration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

COMPANY_DOMAINS: dict[str, tuple[str, ...]] = {
    # P0
    "bytedance": ("jobs.bytedance.com",),
    "tencent": ("join.qq.com", "careers.tencent.com"),
    "alibaba": ("talent.alibaba.com",),
    "baidu": ("talent.baidu.com",),
    "meituan": ("zhaopin.meituan.com", "career.meituan.com"),
    "xiaohongshu": ("job.xiaohongshu.com",),
    "bilibili": ("jobs.bilibili.com",),
    "dewu": ("careers.dewu.com",),
    "deepseek": ("talent.deepseek.com",),
    "360": ("hr.360.cn",),
    # P1
    "xiaomi": ("hr.xiaomi.com",),
    "minimax": ("minimax.cn", "www.minimax.cn"),
    "jd": ("campus.jd.com",),
    "kimi": ("careers.kimi.com",),
    "ctrip": ("job.ctrip.com", "careers.ctrip.com"),
    "kuaishou": ("zhaopin.kuaishou.cn", "campus.kuaishou.cn"),
    "netease": ("campus.163.com",),
    "huawei": ("career.huawei.com",),
    "pdd": ("careers.pddglobalhr.com",),
}

COMPANY_NAMES = {
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

COMPANY_ALIASES = {
    "字节": "bytedance",
    "字节跳动": "bytedance",
    "bytedance": "bytedance",
    "腾讯": "tencent",
    "tencent": "tencent",
    "阿里": "alibaba",
    "阿里巴巴": "alibaba",
    "alibaba": "alibaba",
    "美团": "meituan",
    "meituan": "meituan",
    "百度": "baidu",
    "baidu": "baidu",
    "小红书": "xiaohongshu",
    "xiaohongshu": "xiaohongshu",
    "rednote": "xiaohongshu",
    "哔哩哔哩": "bilibili",
    "b站": "bilibili",
    "bilibili": "bilibili",
    "得物": "dewu",
    "dewu": "dewu",
    "deepseek": "deepseek",
    "深度求索": "deepseek",
    "360": "360",
    "奇虎360": "360",
    "qihoo": "360",
    "小米": "xiaomi",
    "xiaomi": "xiaomi",
    "minimax": "minimax",
    "京东": "jd",
    "jd": "jd",
    "月之暗面": "kimi",
    "kimi": "kimi",
    "moonshot": "kimi",
    "携程": "ctrip",
    "ctrip": "ctrip",
    "快手": "kuaishou",
    "kuaishou": "kuaishou",
    "网易": "netease",
    "netease": "netease",
    "163": "netease",
    "华为": "huawei",
    "huawei": "huawei",
    "拼多多": "pdd",
    "pinduoduo": "pdd",
    "pdd": "pdd",
}


@dataclass(frozen=True, slots=True)
class TrustedTenant:
    company: str
    provider: str
    host: str
    path_prefix: str
    entry_url: str
    evidence_url: str
    verified_at: date


# Only these exact tenants are trusted. ``jobs.feishu.cn`` and
# ``app.mokahr.com`` as a whole are deliberately NOT trusted.
TRUSTED_TENANTS: tuple[TrustedTenant, ...] = (
    TrustedTenant(
        company="minimax",
        provider="feishu",
        host="vrfi1sk8a0.jobs.feishu.cn",
        path_prefix="/",
        entry_url="https://vrfi1sk8a0.jobs.feishu.cn/379481/",
        evidence_url="https://minimax.cn/careers",
        verified_at=date(2026, 10, 21),
    ),
    TrustedTenant(
        company="kimi",
        provider="moka",
        host="app.mokahr.com",
        path_prefix="/apply/moonshot/148506",
        entry_url="https://app.mokahr.com/apply/moonshot/148506#/jobs",
        evidence_url="https://careers.kimi.com/campus",
        verified_at=date(2026, 10, 21),
    ),
    TrustedTenant(
        company="ctrip",
        provider="moka",
        host="app.mokahr.com",
        path_prefix="/campus-recruitment/trip/117988",
        entry_url="https://app.mokahr.com/campus-recruitment/trip/117988#/jobs",
        evidence_url="https://careers.ctrip.com/",
        verified_at=date(2026, 10, 21),
    ),
)


@dataclass(frozen=True, slots=True)
class OfficialUrl:
    company: str
    url: str
    url_type: str = "official_job_detail"
    source_kind: str = "official"
    tenant_host: str | None = None
    tenant_path_prefix: str | None = None


_DETAIL_MARKERS = (
    "/detail",
    "/position/",
    "/position-detail",
    "/positions/",
    "/post.html",
    "/jobs/detail/",
    "/off-campus/",
    "/campus/position/",
    "/experienced/position/",
    "/job/",
    "/jobs/",
    "/careers/",
    "/career/",
    "/social/",
    "/campus/",
    "/post",
    "/apply",
    "/join",
    "/openings",
)
_GENERIC_PATHS = {
    "",
    "/",
    "/jobs",
    "/jobs/",
    "/jobs/list",
    "/careers",
    "/careers/",
    "/career",
    "/career/",
    "/campus",
    "/campus/",
    "/social",
    "/social/",
    "/intern",
    "/internship",
    "/positions",
    "/positions/",
    "/web/home",
    "/hr",
    "/hr/",
    "/index",
    "/index/",
}
_LIST_MARKERS = ("/list", "/search", "/jobs", "/positions", "/campus", "/social")


def resolve_company(value: str | None) -> str | None:
    if not value:
        return None
    return COMPANY_ALIASES.get(value.strip().lower()) or COMPANY_ALIASES.get(value.strip())


def official_domains_for(company_keys: list[str]) -> list[str]:
    domains: list[str] = []
    for key in company_keys:
        domains.extend(COMPANY_DOMAINS.get(key, ()))
    return list(dict.fromkeys(domains))


def _tenant_matches_path(tenant: TrustedTenant, path: str) -> bool:
    prefix = tenant.path_prefix.rstrip("/") or "/"
    if prefix == "/":
        return True
    return path == prefix or path.startswith(f"{prefix}/")


def tenant_for(host: str, path: str, *, company: str | None = None) -> TrustedTenant | None:
    normalized_host = host.lower()
    for tenant in TRUSTED_TENANTS:
        if tenant.host != normalized_host:
            continue
        if company is not None and tenant.company != company:
            continue
        if _tenant_matches_path(tenant, path):
            return tenant
    return None


def search_domains_for(company_keys: list[str]) -> list[str]:
    domains = official_domains_for(company_keys)
    for key in company_keys:
        for tenant in TRUSTED_TENANTS:
            if tenant.company == key and tenant.host not in domains:
                domains.append(tenant.host)
    return domains


# Backward-compatible name used by the discovery service.
def domains_for(company_keys: list[str]) -> list[str]:
    return search_domains_for(company_keys)


def company_for_host(host: str) -> str | None:
    normalized = host.lower()
    for key, domains in COMPANY_DOMAINS.items():
        if normalized in domains:
            return key
    return None


def _query_has_list_filter(query: str) -> bool:
    lowered = query.lower()
    return any(
        key in lowered for key in ("positionname=", "keyword=", "page=", "pagenum=", "search=")
    )


def _is_detail_path(path: str, query: str = "") -> bool:
    lowered = path.lower()
    if lowered in _GENERIC_PATHS or lowered.rstrip("/") in _GENERIC_PATHS:
        return False
    if any(part in lowered for part in ("/jobs/list", "/web/position?", "/search")):
        return False
    query_lower = query.lower()
    if _query_has_list_filter(query_lower):
        return False
    if lowered.rstrip("/").endswith(("/position", "/positions")) and not any(
        key in query_lower for key in ("positionid=", "jobid=", "postid=", "id=")
    ):
        return False
    return any(marker in lowered for marker in _DETAIL_MARKERS) or "position" in lowered


def _is_official_detail(path: str, query: str, company: str) -> bool:
    # NetEase's ``/app/job/position?id=`` is a project/list page, not a job
    # detail. The real detail path is ``/app/detail/index?id=``.
    if company == "netease" and path.lower().startswith("/app/job/position"):
        return False
    return _is_detail_path(path, query)


def _is_ats_detail(tenant: TrustedTenant, path: str, fragment: str) -> bool:
    if tenant.provider == "feishu":
        # Observed real links:
        #   /379481/position/<id>/detail
        #   /379481/m/position/<id>/detail
        return bool(re.search(r"/position/[^/]+/detail/?$", path, re.I))
    if tenant.provider == "moka":
        # Observed real links use a fragment: #/job/<uuid>
        return bool(re.search(r"(?:^|/)job/[^/?#]+", fragment, re.I))
    return _is_detail_path(path)


def _parse_url(url: str):
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https":
        raise ValueError("只允许 https 官方链接")
    if parsed.username or parsed.password:
        raise ValueError("链接不能包含凭据")
    if parsed.port not in (None, 443):
        raise ValueError("不允许非常规端口")
    if not parsed.hostname:
        raise ValueError("链接缺少主机名")
    return parsed


def analyze_url(url: str) -> OfficialUrl:
    """Classify a URL, including list/landing/untrusted results."""
    parsed = _parse_url(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    company = company_for_host(host)
    tenant: TrustedTenant | None = None
    if company is not None:
        if _is_official_detail(path, parsed.query, company):
            url_type = "official_job_detail"
        elif any(marker in path.lower() for marker in _LIST_MARKERS):
            url_type = "official_job_list"
        else:
            url_type = "recruitment_landing_page"
        source_kind = "official"
    else:
        tenant = tenant_for(host, path)
        if tenant is None:
            return OfficialUrl(
                company="",
                url=url.strip(),
                url_type="unrelated_page",
                source_kind="untrusted",
            )
        company = tenant.company
        if _is_ats_detail(tenant, path, parsed.fragment):
            url_type = "trusted_ats_job_detail"
        elif any(marker in path.lower() for marker in _LIST_MARKERS) or parsed.fragment:
            url_type = "trusted_ats_job_list"
        else:
            url_type = "recruitment_landing_page"
        source_kind = "trusted_ats"

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not key.lower().startswith("utm_") and key.lower() not in {"source", "ref"}
    ]
    fragment = parsed.fragment if tenant is not None and tenant.provider == "moka" else ""
    canonical = urlunsplit(
        (
            "https",
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            urlencode(filtered_query),
            fragment,
        )
    )
    return OfficialUrl(
        company=company,
        url=canonical,
        url_type=url_type,
        source_kind=source_kind,
        tenant_host=tenant.host if tenant else None,
        tenant_path_prefix=tenant.path_prefix if tenant else None,
    )


def classify_url(url: str) -> OfficialUrl:
    """Classify a URL and require a verified job detail page."""
    result = analyze_url(url)
    if result.url_type not in {"official_job_detail", "trusted_ats_job_detail"}:
        raise ValueError("链接不是已验证的职位详情页")
    return result


def canonical_official_url(url: str) -> OfficialUrl:
    """Backward-compatible detail-only canonicalizer.

    ATS details are accepted only when their exact tenant path is configured.
    """
    return classify_url(url)


def inspect_url(url: str) -> OfficialUrl | None:
    """Return classification (including list/landing), or ``None`` if invalid."""
    try:
        return analyze_url(url)
    except ValueError:
        return None


def search_query_with_domains(text: str, domains: list[str]) -> str:
    site_terms = " OR ".join(f"site:{domain}" for domain in domains)
    return f"({site_terms}) {text}".strip()
