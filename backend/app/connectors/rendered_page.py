"""Read one user-submitted public job page with a real browser.

Why this exists: most Chinese tech career sites render the job detail client
side, so an HTTP GET returns an empty shell and the page cannot be parsed
server-side. A headless browser sees what the user sees, which is the only way
to turn "paste a link" into a usable JD without reverse engineering each site.

Boundaries (deliberate, not configurable per request):

- public pages only: no login, no captcha bypass, no cookie reuse;
- one URL per call, no crawling, no pagination;
- strict SSRF guard: http(s) only, standard ports, no credentials, every
  resolved address must be public;
- the final URL after redirects is validated again.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.connectors.errors import ConnectorParseError, UnsafeUrlError
from app.core.config import Settings

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

MAX_DESCRIPTION = 20_000
MAX_WAIT_MS = 8_000

JD_MARKERS = (
    "职位描述",
    "岗位描述",
    "岗位职责",
    "工作职责",
    "工作内容",
    "任职要求",
    "岗位要求",
    "职位要求",
    "任职资格",
    "Job Description",
)

# Used only to prefill a hint; the user reviews every field before saving.
CITY_HINTS = (
    "北京",
    "上海",
    "深圳",
    "广州",
    "杭州",
    "成都",
    "南京",
    "武汉",
    "西安",
    "苏州",
    "长沙",
    "厦门",
    "合肥",
    "重庆",
    "天津",
    "济南",
    "青岛",
    "郑州",
    "珠海",
    "东莞",
    "新加坡",
    "香港",
    "远程",
)


def assert_public_url(url: str) -> str:
    """Reject anything that is not a public http(s) page."""
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise UnsafeUrlError("URL 无法解析") from exc
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("仅允许 http/https 链接")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("链接不允许包含账号密码")
    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeUrlError("链接缺少域名")
    if parsed.port not in {None, 80, 443}:
        raise UnsafeUrlError("只允许 80/443 端口")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise UnsafeUrlError("链接指向的不是公网地址")
        return url.strip()

    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"域名无法解析：{host}") from exc
    for entry in addresses:
        ip = ipaddress.ip_address(entry[4][0])
        if not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local:
            raise UnsafeUrlError(f"{host} 解析到非公网地址")
    return url.strip()


@dataclass
class PageSnapshot:
    url: str
    final_url: str
    title: str | None = None
    description: str | None = None
    city: str | None = None
    site_name: str | None = None
    warnings: list[str] = field(default_factory=list)


_EXTRACT_JS = """
(markers) => {
  const txt = (el) => (el && el.innerText ? el.innerText.trim() : "");
  const pickTitle = () => {
    const og = document.querySelector('meta[property="og:title"]');
    const ogText = og ? (og.getAttribute("content") || "").trim() : "";
    if (ogText) return ogText;
    const h1 = document.querySelector("h1");
    if (h1 && txt(h1)) return txt(h1);
    return (document.title || "").trim();
  };
  const body = txt(document.body);
  const hits = [];
  for (const el of document.querySelectorAll("article, main, section, div, td")) {
    const t = txt(el);
    if (t.length < 220 || t.length > 20000) continue;
    if (!markers.some((m) => t.includes(m))) continue;
    hits.push(t);
  }
  // The innermost matching container wins; the outermost would include the
  // whole navigation and footer.
  hits.sort((a, b) => a.length - b.length);
  let description = hits.length ? hits[0] : null;
  if (!description) {
    for (const m of markers) {
      const i = body.indexOf(m);
      if (i > 0) {
        description = body.slice(Math.max(0, i - 600), i + 4000);
        break;
      }
    }
  }
  return {
    title: pickTitle(),
    description,
    siteName: (document.querySelector('meta[property="og:site_name"]') || {}).content || "",
  };
}
"""


class RenderedPageReader:
    """One-shot page reader: open, wait, extract title + JD text."""

    def __init__(self, settings: Settings, executable_path: str | None = None) -> None:
        self._settings = settings
        self._executable = executable_path or getattr(
            settings, "playwright_chromium_executable", None
        )

    def available(self) -> tuple[bool, str]:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            return False, "未安装 playwright，无法解析前端渲染页面"
        return True, "可用"

    def read(self, url: str) -> PageSnapshot:
        from playwright.sync_api import sync_playwright

        target = assert_public_url(url)
        with sync_playwright() as pw:
            launch_kwargs: dict[str, Any] = {"headless": True}
            if self._executable:
                launch_kwargs["executable_path"] = self._executable
            browser = pw.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN")
                page = context.new_page()
                # Only http(s) navigation is allowed; anything else is aborted.
                page.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if route.request.url.split(":", 1)[0] not in {"http", "https"}
                        else route.continue_()
                    ),
                )
                try:
                    page.goto(target, wait_until="domcontentloaded", timeout=30_000)
                except Exception as exc:
                    raise ConnectorParseError(f"打不开这个页面：{type(exc).__name__}") from exc

                assert_public_url(page.url)  # re-check after redirects
                page.wait_for_timeout(1200)
                # Trigger lazy-loaded JD blocks.
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(MAX_WAIT_MS // 2)

                data = page.evaluate(_EXTRACT_JS, list(JD_MARKERS))
                title = (data.get("title") or "").strip() or None
                description = (data.get("description") or "").strip() or None
                site_name = (data.get("siteName") or "").strip() or None
                final_url = page.url
                context.close()
            finally:
                browser.close()

        if not description or len(description) < 80:
            raise ConnectorParseError(
                "没能从这个页面读到 JD 正文（可能需要登录，或详情是动态加载）"
            )
        warnings: list[str] = []
        if len(description) > MAX_DESCRIPTION:
            description = description[:MAX_DESCRIPTION]
            warnings.append(f"正文超过 {MAX_DESCRIPTION} 字，已截断")
        if site_name and title and site_name in title:
            title = title.replace(site_name, "").strip(" -|·") or title

        return PageSnapshot(
            url=target,
            final_url=final_url,
            title=title,
            description=description,
            city=self._guess_city(description),
            site_name=site_name,
            warnings=warnings,
        )

    @staticmethod
    def _guess_city(text: str | None) -> str | None:
        """Only returns a city when the page states it near a location label."""
        if not text:
            return None
        head = text[:1200]
        for label in ("工作地点", "工作城市", "城市", "地点", "Location"):
            index = head.find(label)
            if index < 0:
                continue
            window = head[index : index + 60]
            for city in CITY_HINTS:
                if city in window:
                    return city
        return None
