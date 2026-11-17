"""Browser-rendered job search for SPA career sites.

Why this exists: most large Chinese tech career sites publish no plain JSON API.
The listing page is a single-page app whose XHR requests are signed by front-end
code (ByteDance ``_signature``, Xiaohongshu ``x-s``/``x-s-common``). Those
signatures are produced by obfuscated bundles and rotate, so replaying requests
server-side is not something we can maintain. Fetching the HTML with plain HTTP
returns an empty shell, which is exactly why such companies used to end up as
unverifiable "candidate links".

So instead of reverse engineering each signature, we let a real browser open the
official public search page and capture the JSON responses it receives. The
browser computes whatever signature the site wants; we only read response bodies.

Boundaries kept on purpose:
- public pages only: no login, no cookies, no captcha bypass;
- one page load per (company, keyword), bounded element count;
- the parser is heuristic, so every mapped job must still pass the normal
  normalization/validation step before it reaches the job library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.connectors.errors import ConnectorParseError
from app.connectors.schemas import ConnectorHealth, RawJob
from app.core.config import Settings
from app.db.models.enums import JobSourceMethod, JobStatus, VerificationStatus

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

TITLE_KEYS = (
    "title",
    "positionname",
    "jobname",
    "postname",
    "positiontitle",
    "name",
)
STRONG_TITLE_KEYS = TITLE_KEYS[:-1]
DESC_KEYS = (
    "description",
    "jobdesc",
    "positiondesc",
    "positiondescription",
    "jobdescription",
    "jobduty",
    "responsibility",
    "duty",
    "workcontent",
    "jobresponsibility",
)
REQ_KEYS = (
    "requirement",
    "requirements",
    "jobrequirement",
    "positionrequirement",
    "qualification",
    "jobqualification",
)
CITY_KEYS = (
    "cityinfo",
    "cityname",
    "workcity",
    "workplace",
    "worklocation",
    "locationname",
    "city",
    "location",
    "citylist",
    "workcitylist",
    "citynamelist",
)
# Each site names the org unit differently: Meituan has ``department``,
# ByteDance only ``job_category``/``job_function``, Xiaohongshu
# ``directionName``. Without these the library showed an empty 部门 for almost
# every posting even though the page displays one.
DEPARTMENT_KEYS = (
    "department",
    "departmentname",
    "bg",
    "bgname",
    "jobfamily",
    "jobfamilygroup",
    "jobcategory",
    "jobfunction",
    "directionname",
    "subdirectionname",
    "jobprojectname",
    "postcodename",
)

URL_KEYS = ("joburl", "positionurl", "posturl", "detailurl", "url", "link")
ID_KEYS = ("jobid", "positionid", "positionid", "jobunionid", "postid", "id", "code")
HIRE_TYPE_KEYS = (
    "recruittype",
    "recruittypename",
    "hiretype",
    "jobtype",
    "positiontype",
    "positiontypename",
    "recruitmenttype",
    "campusorintern",
)

# Sections inside one combined JD blob ("工作职责 … 工作要求 …").
JD_SECTION_MARKERS = (
    "工作要求",
    "任职要求",
    "任职资格",
    "岗位要求",
    "职位要求",
    "任职条件",
)


def split_jd(text: str | None) -> tuple[str | None, str | None]:
    """Split a combined JD blob into (responsibilities, requirements)."""

    if not text:
        return None, None
    for marker in JD_SECTION_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            desc = text[:idx].strip(" ：:；;\n\t")
            req = text[idx + len(marker) :].strip(" ：:；;\n\t")
            return (desc or None), (req or None)
    return text.strip() or None, None


@dataclass(frozen=True)
class RenderedSourceSpec:
    """Everything needed to search one company site; one entry per company."""

    source_type: str
    company: str
    search_url: str  # "{keyword}" placeholder
    job_type: str | None = None
    recruitment_program: str | None = None
    detail_url: str | None = None  # "{id}" placeholder
    wait_ms: int = 5000
    min_wait_ms: int = 1200
    note: str = ""
    # Most of these SPAs ignore the ``?keyword=`` query string and only search
    # when the keyword goes through their own search box, so the input has to be
    # driven explicitly. Without this the "search" silently returns page one.
    search_input: str | None = None
    # Some sites scope campus results through a tab (Meituan: 应届校招) rather
    # than the URL; clicking it is what keeps 社招 out of the result set.
    pre_click_text: str | None = None


def _norm(value: str) -> str:
    return value.lower().replace("_", "").replace("-", "")


def _as_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        parent = _as_text(value.get("parent")) if isinstance(value.get("parent"), dict) else None
        for key in ("i18n_name", "name", "showTitle", "title", "label", "cityName"):
            found = _as_text(value.get(key))
            if found:
                # ByteDance nests hire type as {name: 实习, parent: {name: 校招}};
                # keeping both parts lets us classify internship vs campus.
                return f"{parent}/{found}" if parent and parent != found else found
    if isinstance(value, list):
        parts = [_as_text(item) for item in value]
        joined = " / ".join(part for part in parts if part)
        return joined or None
    return None


def _pick(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    lowered = {_norm(key): key for key in item}
    for wanted in keys:
        real = lowered.get(_norm(wanted))
        if real is None:
            continue
        text = _as_text(item.get(real))
        if text:
            return text
    return None


def _score_list(rows: list[Any]) -> int:
    if not rows or not all(isinstance(row, dict) for row in rows[:5]):
        return 0
    sample = rows[:5]
    # "name" alone is not enough: city/enum lists use it too. A job list either
    # carries a dedicated title column or ships JD text alongside.
    titles = sum(1 for row in sample if _pick(row, STRONG_TITLE_KEYS))
    descs = sum(1 for row in sample if _pick(row, DESC_KEYS) or _pick(row, REQ_KEYS))
    ids = sum(1 for row in sample if _pick(row, ID_KEYS))
    if titles < len(sample) * 0.6 and descs < len(sample) * 0.6:
        return 0
    return len(rows) + descs * 40 + ids * 10


def find_job_list(payload: Any, depth: int = 0) -> list[dict[str, Any]] | None:
    """Depth-first search for the JSON array that looks most like a job list."""
    if depth > 8:
        return None
    best: tuple[int, list[dict[str, Any]]] | None = None
    if isinstance(payload, list):
        score = _score_list(payload)
        if score:
            best = (score, [row for row in payload if isinstance(row, dict)])
    elif isinstance(payload, dict):
        for value in payload.values():
            found = find_job_list(value, depth + 1)
            if not found:
                continue
            score = _score_list(found)
            if best is None or score > best[0]:
                best = (score, found)
    return best[1] if best else None


def _published_at(row: dict[str, Any]) -> datetime | None:
    """Convert epoch millis/seconds or an ISO-ish date string to UTC."""
    raw = _pick(
        row,
        (
            "publishtime",
            "pushtime",
            "publishdate",
            "createtime",
            "onlinetime",
            "firstposttime",
            "refreshtime",
            "lastposttime",
            "updatetime",
        ),
    )
    if not raw:
        return None
    text = raw.strip()
    if "-" in text or "/" in text:
        candidate = text.replace("/", "-")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(candidate).replace(tzinfo=UTC)
        except ValueError:
            return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 10:
        return None
    seconds = int(digits[:13]) / 1000 if len(digits) >= 13 else int(digits[:10])
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None


CITY_SEPARATORS = ("|", "/", ",", "，", "、", ";", "；")


def _city(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value
    for sep in CITY_SEPARATORS:
        cleaned = cleaned.replace(sep, " ")
    parts = cleaned.split()
    if not parts:
        return None
    return parts[0].removesuffix("总部").removesuffix("市") or parts[0]


@dataclass
class _Capture:
    urls: list[str] = field(default_factory=list)
    jobs: list[dict[str, Any]] = field(default_factory=list)


class RenderedJobSearch:
    """Runs a headless browser over one official search page and maps the JSON."""

    def __init__(self, settings: Settings, executable_path: str | None = None) -> None:
        self._settings = settings
        self._executable = executable_path or getattr(
            settings, "playwright_chromium_executable", None
        )

    def available(self) -> tuple[bool, str]:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            return False, "未安装 playwright，无法渲染前端页面"
        return True, "可用"

    def search(
        self,
        spec: RenderedSourceSpec,
        keyword: str | None,
        limit: int,
    ) -> list[RawJob]:
        from playwright.sync_api import sync_playwright

        target = spec.search_url.format(keyword=(keyword or "").strip())
        captured = _Capture()
        deadline_ms = spec.wait_ms
        wants_typed_search = bool((keyword or "").strip() and spec.search_input)
        # Responses that land before the keyword is applied are page-one filler:
        # reading them would silently ignore the keyword.
        gate = {"open": not wants_typed_search}

        with sync_playwright() as pw:
            launch_kwargs: dict[str, Any] = {"headless": True}
            if self._executable:
                launch_kwargs["executable_path"] = self._executable
            browser = pw.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN")
                page = context.new_page()

                def on_response(response) -> None:
                    if not gate["open"]:
                        return
                    if len(captured.jobs) >= limit:
                        return
                    if "json" not in response.headers.get("content-type", ""):
                        return
                    try:
                        payload = response.json()
                    except Exception:
                        return
                    rows = find_job_list(payload)
                    if not rows:
                        return
                    captured.urls.append(response.url)
                    known = {
                        (_pick(row, TITLE_KEYS) or "", _pick(row, CITY_KEYS) or "")
                        for row in captured.jobs
                    }
                    for row in rows:
                        key = (_pick(row, TITLE_KEYS) or "", _pick(row, CITY_KEYS) or "")
                        if key in known:
                            continue
                        known.add(key)
                        captured.jobs.append(row)

                page.on("response", on_response)
                try:
                    page.goto(target, wait_until="domcontentloaded", timeout=35_000)
                except Exception as exc:  # page may still have rendered
                    raise ConnectorParseError(f"打开搜索页失败：{type(exc).__name__}") from exc
                page.wait_for_timeout(spec.min_wait_ms)
                if spec.pre_click_text:
                    self._click_text(page, spec.pre_click_text)
                if wants_typed_search and self._fill_keyword(
                    page, spec.search_input, keyword or ""
                ):
                    # Drop whatever the unfiltered page loaded, then open the gate
                    # right before submitting: the keyword XHR must be captured,
                    # and no pre-keyword row may sneak in.
                    captured.jobs.clear()
                    captured.urls.clear()
                    page.keyboard.press("Enter")
                gate["open"] = True
                waited = 0
                next_scroll = 1200
                while waited < deadline_ms and len(captured.jobs) < limit:
                    page.wait_for_timeout(500)
                    waited += 500
                    if waited >= next_scroll:
                        # Infinite-scroll lists (ByteDance/Xiaohongshu/Meituan)
                        # only request the next page after a real scroll; just
                        # waiting used to cap every crawl at the first 10 rows,
                        # which made the deeper discover modes do nothing.
                        page.mouse.wheel(0, 2400)
                        # ByteDance renders the list in an inner scroll container,
                        # so a window-level wheel moves nothing there.
                        page.evaluate(
                            "() => {"
                            " const el = [...document.querySelectorAll('div')]"
                            "  .find(d => d.scrollHeight > d.clientHeight + 200);"
                            " if (el) { el.scrollTop = el.scrollHeight; }"
                            " else { window.scrollBy(0, 2400); }"
                            "}"
                        )
                        # Some lists page behind a "load more" button instead of
                        # scroll-triggered fetching.
                        for label in ("加载更多", "查看更多", "更多岗位"):
                            try:
                                page.get_by_text(label, exact=False).first.click(timeout=800)
                                break
                            except Exception:
                                continue
                        next_scroll += 1200
                context.close()
            finally:
                browser.close()

        if not captured.jobs:
            raise ConnectorParseError(
                f"{spec.company} 搜索页未返回可识别的岗位数据（可能需要登录或已改版）"
            )
        now = datetime.now(UTC)
        jobs: list[RawJob] = []
        for row in captured.jobs[:limit]:
            job = self._to_raw_job(spec, row, now)
            if job is not None:
                jobs.append(job)
        return jobs

    @staticmethod
    def _click_text(page: Any, text: str) -> bool:
        """Click a nav/tab by visible text; a miss must not abort the search."""
        try:
            page.get_by_text(text, exact=True).first.click(timeout=6000)
            page.wait_for_timeout(1200)
            return True
        except Exception:
            return False

    @staticmethod
    def _fill_keyword(page: Any, selector: str | None, keyword: str) -> bool:
        """Type the keyword into the site's own search box (submit is separate)."""
        if not selector:
            return False
        try:
            box = page.locator(selector).first
            box.wait_for(state="visible", timeout=8000)
            box.click()
            box.fill("")
            box.fill(keyword)
            page.wait_for_timeout(400)
            return True
        except Exception:
            return False

    def _to_raw_job(
        self,
        spec: RenderedSourceSpec,
        row: dict[str, Any],
        now: datetime,
    ) -> RawJob | None:
        title = _pick(row, TITLE_KEYS)
        if not title:
            return None
        source_job_id = _pick(row, ID_KEYS) or title
        detail = _pick(row, URL_KEYS)
        if detail and detail.startswith("/"):
            base = spec.search_url.split("/", 3)
            detail = f"{base[0]}//{base[2]}{detail}"
        if not detail and spec.detail_url:
            detail = spec.detail_url.format(id=source_job_id)
        if not detail:
            detail = spec.search_url.format(keyword="")
        city_text = _pick(row, CITY_KEYS)
        description = _pick(row, DESC_KEYS)
        requirement = _pick(row, REQ_KEYS)
        if not requirement:
            # Bilibili/Bytedance-ish sites ship one blob with both sections.
            description, requirement = split_jd(description)
        hire_type = _pick(row, HIRE_TYPE_KEYS)
        job_type = spec.job_type
        if hire_type:
            if "实习" in hire_type:
                job_type = "internship"
            elif "校" in hire_type or "应届" in hire_type:
                job_type = "campus"
        return RawJob(
            source_type=spec.source_type,
            source_key=spec.source_type,
            source_job_id=source_job_id,
            company=spec.company,
            title=title,
            source_url=detail,
            description=description,
            department=_pick(row, DEPARTMENT_KEYS),
            location_text=city_text,
            city=_city(city_text),
            job_type=job_type,
            recruitment_program=spec.recruitment_program,
            requirements=[requirement] if requirement else [],
            published_at=_published_at(row),
            fetched_at=now,
            raw_payload={"title": title, "site": spec.search_url.split("/")[2]},
            is_demo=False,
            status=JobStatus.OPEN,
            source_method=JobSourceMethod.PUBLIC_PAGE,
            verification_status=VerificationStatus.VERIFIED,
            verified_at=now,
        )

    def health_check(self, source_config: dict[str, Any]) -> ConnectorHealth:
        ok, message = self.available()
        return ConnectorHealth(configured=ok, ok=ok, message=message)


def parse_json_lenient(text: str) -> Any:
    """Small helper kept for fixtures/tests."""

    try:
        return json.loads(text)
    except ValueError as exc:
        raise ConnectorParseError("响应不是合法 JSON") from exc
