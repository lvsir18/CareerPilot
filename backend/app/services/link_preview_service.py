"""Preview a job page the user pasted, without writing anything.

The Baidu importer only understands one site. Every other company renders the
detail page in the browser, so this service opens the page once and returns a
draft (title / company / city / JD text) for the user to confirm. Nothing is
stored until the user saves it as a private candidate.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.connectors.errors import ConnectorParseError, UnsafeUrlError
from app.connectors.rendered_page import RenderedPageReader
from app.core.config import Settings
from app.core.errors import AppError
from app.search.domains import COMPANY_DOMAINS, COMPANY_NAMES, TRUSTED_TENANTS
from app.services.job_sections import split_job_sections

# Campus sub-sites sit on different hosts than the domains used for official
# verification, so they are only used to *label* a preview. Adding them to
# COMPANY_DOMAINS would widen the verification whitelist, which is not the goal.
_CAMPUS_HOSTS: dict[str, str] = {
    "campus.dewu.com": "得物",
    "campus.163.com": "网易",
    "campus.jd.com": "京东",
    "campus.kuaishou.cn": "快手",
    "zhaopin.kuaishou.cn": "快手",
    "campus.360.cn": "360",
    "360campus.zhiye.com": "360",
    "xiaomi.jobs.f.mioffice.cn": "小米",
    "campus-talent.alibaba.com": "阿里巴巴",
    "career.huawei.com": "华为",
    "hr.xiaomi.com": "小米",
    "job.ctrip.com": "携程",
    "careers.pddglobalhr.com": "拼多多",
    "talent.baidu.com": "百度",
    "jobs.bytedance.com": "字节跳动",
    "job.xiaohongshu.com": "小红书",
    "jobs.bilibili.com": "哔哩哔哩",
    "zhaopin.meituan.com": "美团",
    "talent.alibaba.com": "阿里巴巴",
}


def _company_from_host(host: str) -> str | None:
    for key, domains in COMPANY_DOMAINS.items():
        for domain in domains:
            if host == domain or host.endswith(f".{domain}"):
                name = COMPANY_NAMES.get(key)
                if name:
                    return name
    for domain, name in _CAMPUS_HOSTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return name
    return None


def _company_from_url(url: str) -> str | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    for tenant in TRUSTED_TENANTS:
        if host == tenant.host and (
            parsed.path == tenant.path_prefix
            or parsed.path.startswith(tenant.path_prefix.rstrip("/") + "/")
        ):
            return COMPANY_NAMES.get(tenant.company)
    # Public link on https://talent.deepseek.com/ (checked 2026-10-24).
    # This labels a private draft; it does not expand the verified-job allowlist.
    if host == "app.mokahr.com" and (
        parsed.path == "/social-recruitment/high-flyer/140576"
        or parsed.path.startswith("/social-recruitment/high-flyer/140576/")
    ):
        return "DeepSeek"
    return _company_from_host(host)


def _company_from_site_name(site_name: str | None) -> str | None:
    if not site_name:
        return None
    for name in COMPANY_NAMES.values():
        if name and name in site_name:
            return name
    return None


class LinkPreviewService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def preview(self, url: str) -> dict[str, Any]:
        reader = RenderedPageReader(self._settings)
        ok, message = reader.available()
        if not ok:
            raise AppError("RENDER_UNAVAILABLE", message, status_code=503)
        try:
            snapshot = reader.read(url)
        except UnsafeUrlError as exc:
            raise AppError("UNSAFE_URL", str(exc), status_code=422) from exc
        except ConnectorParseError as exc:
            raise AppError(
                "LINK_PREVIEW_FAILED",
                f"{exc.message}。可以手动复制 JD 后粘贴保存。",
                status_code=422,
            ) from exc

        company = (
            _company_from_url(snapshot.final_url)
            or _company_from_url(snapshot.url)
            or _company_from_site_name(snapshot.site_name)
        )
        warnings = list(snapshot.warnings)
        if not company:
            warnings.append("未能识别企业，请手动填写")
        if not snapshot.city:
            warnings.append("未能识别城市，可留空")
        if not snapshot.job_type:
            warnings.append("未能确定唯一岗位类型，请对照官网核对")
        sections = split_job_sections(snapshot.description)
        return {
            "url": snapshot.url,
            "final_url": snapshot.final_url,
            "title": snapshot.title,
            "company": company,
            "city": snapshot.city,
            "location_text": snapshot.location_text,
            "job_type": snapshot.job_type,
            "description": sections.description,
            "requirements": sections.requirements,
            "additional_info": sections.additional_info,
            "warnings": warnings,
            "source": "rendered",
        }
