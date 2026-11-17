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
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.connectors.errors import ConnectorParseError, UnsafeUrlError
from app.core.config import Settings
from app.db.models.enums import JobStatus

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
    "工作要求",
    "任职条件",
    "加分项",
    "福利待遇",
    "你将会负责",
    "我们期望你",
    "Job Description",
    "Responsibilities",
    "Requirements",
    "Qualifications",
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
    "南通",
    "廊坊",
    "乌兰察布",
    "石家庄",
    "温州",
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


# Only an explicit closure statement may close a posting. Anything ambiguous
# (timeout, login wall, redirect to a list, empty body) must stay UNKNOWN: a
# false "closed" hides a real opening and, worse, archives it.
_CLOSED_MARKERS = (
    "职位已下架",
    "该职位已下架",
    "岗位已下架",
    "职位已关闭",
    "该岗位已关闭",
    "岗位已关闭",
    "招聘已结束",
    "职位已结束",
    "岗位已下线",
    "该职位已下线",
    "已停止招聘",
    "position is closed",
    "no longer accepting applications",
    "job is no longer available",
)
_LOGIN_MARKERS = ("请登录", "登录后查看", "sign in to continue", "请先登录")

_DETAIL_PATH_RE = re.compile(
    r"/(?:detail|job-info|job-details|position|positions|post|job|jobs)/[^/?#]+", re.I
)


@dataclass
class PageSnapshot:
    url: str
    final_url: str
    title: str | None = None
    description: str | None = None
    city: str | None = None
    site_name: str | None = None
    job_type: str | None = None
    location_text: str | None = None
    warnings: list[str] = field(default_factory=list)
    # open / closed / unknown + the sentence that justified it.
    status: JobStatus = JobStatus.UNKNOWN
    status_evidence: str | None = None
    # Structured labels the page shows next to the JD (在招业务 / 部门 / 更新于 …).
    # They are plain text on every site, just with different wording.
    department: str | None = None
    published_at: datetime | None = None
    recruitment_program: str | None = None
    job_category: str | None = None


# Each site renders the same facts as plain labels next to the JD; only the
# wording differs (阿里 “在招业务/更新于”, 美团 “部门：/更新时间：”).
_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "department": ("在招业务", "所属部门", "所属业务", "业务集团", "部门"),
    "published_at": ("更新于", "更新时间", "发布时间", "发布日期", "上线时间"),
    "city": ("工作地点", "工作城市", "办公地点", "城市"),
    "recruitment_program": ("招聘项目", "招聘类型", "项目"),
    "job_category": ("职位类别", "职位类型", "岗位类别"),
}
_LABEL_VALUE_MAX = 120


def _labeled_fields(text: str) -> dict[str, str]:
    """Pull ``标签：值`` / ``标签<换行>值`` pairs out of the page text."""
    lines = [line.strip() for line in (text or "").splitlines()]
    found: dict[str, str] = {}
    for index, line in enumerate(lines):
        if not line or len(line) > _LABEL_VALUE_MAX:
            continue
        for name, labels in _FIELD_LABELS.items():
            if name in found:
                continue
            for label in labels:
                if not line.startswith(label):
                    continue
                rest = line[len(label) :].lstrip(":： \t")
                if rest:
                    found[name] = rest
                elif index + 1 < len(lines):
                    nxt = lines[index + 1]
                    if nxt and len(nxt) <= _LABEL_VALUE_MAX:
                        found[name] = nxt
                break
    return found


def _parse_label_date(raw: str | None) -> datetime | None:
    """``2026-03-26`` / ``2026/11/16`` → UTC datetime (date precision)."""
    if not raw:
        return None
    match = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", raw)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return None


def detect_posting_status(
    *,
    title: str | None,
    description: str | None,
    target_url: str,
    final_url: str,
) -> tuple[JobStatus, str | None]:
    """Decide a posting's state from one page read, conservatively."""
    text = f"{title or ''}\n{description or ''}"
    for marker in _CLOSED_MARKERS:
        index = text.lower().find(marker.lower())
        if index >= 0:
            excerpt = text[max(0, index - 40) : index + len(marker) + 40].replace("\n", " ")
            return JobStatus.CLOSED, f"页面明确提示「{marker}」：{excerpt.strip()}"
    for marker in _LOGIN_MARKERS:
        if marker.lower() in text.lower():
            return JobStatus.UNKNOWN, f"页面要求登录（{marker}），无法确认岗位状态"
    # A detail URL that ends up on a list/home page is a redirect, not a closure.
    if _DETAIL_PATH_RE.search(target_url) and not _DETAIL_PATH_RE.search(final_url):
        return JobStatus.UNKNOWN, f"详情页跳转到 {final_url}，无法确认岗位状态"
    if not description or len(description) < 80:
        return JobStatus.UNKNOWN, "页面正文为空或过短，无法确认岗位状态"
    return JobStatus.OPEN, f"读到官方详情正文（{len(description)} 字）"


_EXTRACT_JS = Path(__file__).with_name("job_detail_extract.js").read_text(encoding="utf-8")


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
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        target = assert_public_url(url)
        with sync_playwright() as pw:
            launch_kwargs: dict[str, Any] = {"headless": True}
            if self._executable:
                launch_kwargs["executable_path"] = self._executable
            browser = pw.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context(
                    user_agent=USER_AGENT, locale="zh-CN", service_workers="block"
                )
                page = context.new_page()
                # Validate requests BEFORE following redirects or loading frames.
                # A public entry page must not become a route into the LAN.
                public_origins: dict[str, bool] = {}

                def route_public(route: Any) -> None:
                    request_url = route.request.url
                    parsed = urlsplit(request_url)
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                    if origin not in public_origins:
                        try:
                            assert_public_url(request_url)
                            public_origins[origin] = True
                        except UnsafeUrlError:
                            public_origins[origin] = False
                    if public_origins[origin]:
                        route.continue_()
                    else:
                        route.abort()

                context.route("**/*", route_public)
                try:
                    page.goto(target, wait_until="domcontentloaded", timeout=30_000)
                except Exception as exc:
                    raise ConnectorParseError(f"打不开这个页面：{type(exc).__name__}") from exc

                assert_public_url(page.url)
                data = self._wait_for_detail(page)
                # Labels like 更新于/在招业务/招聘项目 sit outside the extracted
                # JD block, so keep the whole visible text for them — read it
                # *after* the JD wait, otherwise the SPA is still empty.
                try:
                    page_text = page.inner_text("body")
                except PlaywrightError:
                    page_text = ""
                warnings: list[str] = []
                if urlsplit(page.url).hostname == "career.huawei.com":
                    try:
                        data, direction_warnings = self._huawei_directions(page, data)
                    except PlaywrightError as exc:
                        raise ConnectorParseError(
                            "未能展开官网的岗位方向，请手动选择方向并复制 JD"
                        ) from exc
                    warnings.extend(direction_warnings)
                title = (data.get("title") or "").strip() or None
                description = (data.get("description") or "").strip() or None
                site_name = (data.get("siteName") or "").strip() or None
                metadata = data.get("metadata") or ""
                final_url = page.url
                context.close()
            finally:
                browser.close()

        if not description or len(description) < 80:
            raise ConnectorParseError(
                "没能从这个页面读到 JD 正文（可能需要登录，或详情是动态加载）"
            )
        if len(description) > MAX_DESCRIPTION:
            description = description[:MAX_DESCRIPTION]
            warnings.append(f"正文超过 {MAX_DESCRIPTION} 字，已截断")
        if site_name and title and site_name in title:
            title = title.replace(site_name, "").strip(" -|·") or title

        status, status_evidence = detect_posting_status(
            title=title,
            description=description,
            target_url=target,
            final_url=final_url,
        )
        labeled = _labeled_fields(page_text or description or "")
        return PageSnapshot(
            url=target,
            final_url=final_url,
            title=title,
            description=description,
            city=(
                self._guess_city(metadata)
                or labeled.get("city")
                or self._guess_labeled_city(description)
            ),
            location_text=self._guess_city(metadata) or labeled.get("city"),
            job_type=self._guess_job_type(title, metadata),
            site_name=site_name,
            warnings=warnings,
            status=status,
            status_evidence=status_evidence,
            department=labeled.get("department"),
            published_at=_parse_label_date(labeled.get("published_at")),
            recruitment_program=labeled.get("recruitment_program"),
            job_category=labeled.get("job_category"),
        )

    @staticmethod
    def _wait_for_detail(
        page: Any,
        *,
        allow_direction_prompt: bool = True,
        timeout_ms: int = MAX_WAIT_MS,
        previous_description: str | None = None,
    ) -> dict[str, Any]:
        """Wait for actual JD content to settle, rather than one fixed sleep."""
        started = time.monotonic()
        deadline = started + timeout_ms / 1000
        previous = None
        stable = 0
        data: dict[str, Any] = {}
        while time.monotonic() < deadline:
            page.wait_for_timeout(500)
            data = page.evaluate(_EXTRACT_JS, list(JD_MARKERS))
            text = data.get("description")
            if text == previous_description:
                text = None
            stable = stable + 1 if text and text == previous else 0
            previous = text
            elapsed = time.monotonic() - started
            if (
                stable >= 3
                and elapsed >= 2
                and (len(data.get("sections", [])) >= 2 or elapsed >= 5)
            ):
                break
            if (
                allow_direction_prompt
                and not text
                and urlsplit(page.url).hostname == "career.huawei.com"
                and page.locator(".position-intention .intention-select").count()
            ):
                break
        return data

    @staticmethod
    def _huawei_directions(page: Any, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """The public Huawei detail is blank until a direction is selected.

        Read each public direction and label it explicitly; never silently
        substitute one direction for the aggregate role in the submitted URL.
        """
        selector = page.locator(".position-intention .intention-select")
        if not selector.count():
            return data, []
        selector.click(timeout=2000)
        options = page.locator(".aui-select .node-label")
        # Options are teleported outside the select on the current official UI.
        if not options.count():
            options = page.locator(".aui-popover .node-label")
        names = options.all_text_contents()
        if not names:
            # Restrict to the select's dropdown, never arbitrary page links.
            options = page.locator(
                ".aui-select-dropdown .node-label, .aui-select-panel .node-label"
            )
            names = options.all_text_contents()
        names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        parts: list[str] = []
        missing = 0
        previous_description = None
        deadline = time.monotonic() + 25
        for index, name in enumerate(names[:12]):
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms < 1000:
                missing += len(names[:12]) - index
                break
            if index:
                selector.click(timeout=2000)
            page.get_by_title(name, exact=True).last.click(timeout=2000)
            item = RenderedPageReader._wait_for_detail(
                page,
                allow_direction_prompt=False,
                timeout_ms=min(MAX_WAIT_MS, remaining_ms),
                previous_description=previous_description,
            )
            description = item.get("description")
            if description and description != previous_description:
                parts.append(f"【岗位方向：{name.strip()}】\n{description}")
                previous_description = description
            else:
                missing += 1
        if not parts:
            return data, []
        data["description"] = "\n\n".join(parts)
        warnings = [f"该岗位有多个方向，已按方向保留 {len(parts)} 份正文，请核对并保留意向方向"]
        if missing or len(names) > 12:
            warnings.append("部分岗位方向未能读取，请到官网选择方向后补充 JD")
        return data, warnings

    @staticmethod
    def _guess_city(text: str | None) -> str | None:
        if not text:
            return None
        hits = [(text.find(city), city) for city in CITY_HINTS if city in text]
        # Preserve the site's order and all advertised cities.
        return "/".join(city for _, city in sorted(hits)) or None

    @classmethod
    def _guess_labeled_city(cls, text: str | None) -> str | None:
        if not text:
            return None
        match = re.search(r"(?:工作地点|工作城市|Location)\s*[：:]?([^\n]{0,80})", text, re.I)
        return cls._guess_city(match.group(1)) if match else None

    @staticmethod
    def _guess_job_type(title: str | None, metadata: str) -> str | None:
        text = f"{title or ''}\n{metadata}"
        if "实习" in text or re.search(r"\bintern(?:ship)?\b", text, re.I):
            return "internship"
        if "应届" in text or "校招" in text or "校园招聘" in text:
            return "campus"
        if "全职" in metadata:
            return "full_time"
        return None
