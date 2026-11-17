"""Conservative JD extraction and structuring.

Tavily Extract returns page text or markdown, not a trusted JD schema. This
module only promotes fields that are explicit in the extracted text. Missing or
ambiguous values stay ``None``/empty; callers must not treat the result as a
verified Job until completeness and source checks pass.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlsplit

_RESP_HEADERS = (
    "岗位职责",
    "工作职责",
    "职位职责",
    "职位描述",
    "岗位描述",
    "工作描述",
    "工作内容",
    "你将负责",
    "你将参与",
    "responsibilities",
    "what you will do",
    "what you'll do",
)
_REQ_HEADERS = (
    "任职要求",
    "岗位要求",
    "职位要求",
    "任职资格",
    "工作要求",
    "我们希望你",
    "希望你",
    "requirements",
    "qualifications",
    "what we expect",
)
_SKILL_HEADERS = ("技能要求", "技术栈", "专业技能", "skills", "skill requirements")
_ALL_HEADERS = _RESP_HEADERS + _REQ_HEADERS + _SKILL_HEADERS
_GENERIC_TITLES = {
    "职位详情",
    "岗位详情",
    "招聘详情",
    "招聘",
    "校园招聘",
    "社会招聘",
    "job detail",
    "job description",
    "首页",
    "职位列表",
    "招聘首页",
    "登录",
}
_CITY_WORDS = ("北京", "上海", "深圳", "杭州", "广州", "成都", "南京", "武汉", "苏州", "西安")
_CITY_RE = re.compile(r"(?:工作地点|办公地点|地点|location)\s*[：:]\s*([^\n]{1,80})", re.I)
_DEPT_RE = re.compile(r"(?:部门|所属部门|department)\s*[：:]\s*([^\n]{1,80})", re.I)
_DATE_RE = re.compile(
    r"(?:发布时间|发布日期|更新日期|posted\s*(?:on|date)?|date)\s*[：:]\s*"
    r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
    re.I,
)


@dataclass(slots=True)
class ParsedJD:
    company: str
    title: str | None
    official_url: str
    department: str | None = None
    location: str | None = None
    job_type: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    description: str = ""
    published_date: date | None = None
    official_job_id: str | None = None
    field_sources: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    is_complete: bool = False
    is_open: bool = True
    incomplete_reasons: list[str] = field(default_factory=list)
    raw_content: str = ""


def clean_extracted_text(value: str) -> str:
    """Strip executable/active HTML and preserve readable line breaks."""
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", value)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _heading(line: str) -> tuple[str, str] | None:
    normalized = re.sub(r"[*_`#]+", "", line).casefold().strip(" -:：")
    for header in _RESP_HEADERS:
        if (
            normalized == header
            or normalized.startswith(f"{header}：")
            or normalized.startswith(f"{header}:")
        ):
            return "responsibilities", line
    for header in _REQ_HEADERS:
        if (
            normalized == header
            or normalized.startswith(f"{header}：")
            or normalized.startswith(f"{header}:")
        ):
            return "requirements", line
    for header in _SKILL_HEADERS:
        if (
            normalized == header
            or normalized.startswith(f"{header}：")
            or normalized.startswith(f"{header}:")
        ):
            return "skills", line
    return None


def _clean_bullet(line: str) -> str:
    cleaned = re.sub(r"[*_`]+", "", line)
    return re.sub(r"^[\-*•·\d]+[.)、\s]+", "", cleaned).strip()


_INLINE_HEADER = re.compile(
    r"(岗位职责|工作职责|职位描述|岗位描述|工作描述|工作内容|任职要求|岗位要求|职位要求|"
    r"任职资格|工作要求|技能要求|技术栈)\s*[:：]"
)
_STOP_LINE = re.compile(r"^(投递|分享|立即申请|申请职位|返回|首页|登录|职位已下架)$")


def _section_lines(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {
        "responsibilities": [],
        "requirements": [],
        "skills": [],
    }
    current: str | None = None
    for line in text.splitlines():
        stripped = re.sub(r"[*_`]+", "", line).strip()
        if not stripped:
            continue
        if _STOP_LINE.match(stripped):
            current = None
            continue
        # Some ATS pages put multiple bold headings in one Markdown line.
        matches = list(_INLINE_HEADER.finditer(stripped))
        if matches:
            for index, match in enumerate(matches):
                header = match.group(1)
                found = _heading(header)
                if not found:
                    continue
                current = found[0]
                start = match.end()
                end = matches[index + 1].start() if index + 1 < len(matches) else len(stripped)
                content = _clean_bullet(stripped[start:end])
                if content:
                    sections[current].append(content)
            continue
        found = _heading(stripped)
        if found:
            current = found[0]
            inline = re.split(r"[：:]", stripped, maxsplit=1)
            if len(inline) == 2 and inline[1].strip():
                sections[current].append(_clean_bullet(inline[1]))
            continue
        if current and stripped:
            cleaned = _clean_bullet(stripped)
            if cleaned and len(cleaned) <= 600:
                sections[current].append(cleaned)
    return sections


def _title_from_text(text: str, fallback: str | None) -> tuple[str | None, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Markdown headings and explicit HTML-like headings are strongest.
    for line in lines[:40]:
        heading = re.match(r"^#{1,3}\s+(.+)$", line)
        if not heading:
            continue
        candidate = re.sub(r"[*_`]+", "", heading.group(1)).strip()
        if 2 <= len(candidate) <= 120 and candidate.casefold() not in _GENERIC_TITLES:
            return candidate, "extracted"
    # A search lead title is safer than a navigation line from an ATS shell.
    if fallback and fallback.strip() and fallback.strip().casefold() not in _GENERIC_TITLES:
        return fallback.strip(), "lead_title"
    for line in lines[:40]:
        candidate = re.sub(r"[*_`#]+", "", line).strip(" -:：")
        if not 2 <= len(candidate) <= 120:
            continue
        lowered = candidate.casefold()
        if any(
            key in lowered
            for key in (
                "岗位职责",
                "任职要求",
                "职位描述",
                "职位要求",
                "招聘首页",
                "扫码",
                "登录",
                "隐私政策",
                "copyright",
                "职位已下架",
                "当前职位无法投递",
            )
        ):
            continue
        if lowered in _GENERIC_TITLES or lowered.startswith("image"):
            continue
        if any(char in candidate for char in ("|", "://", "·", "→")):
            continue
        if candidate.count(" ") > 12:
            continue
        return candidate, "extracted"
    return None, "missing"


def _id_from_url(url: str) -> str | None:
    parsed = urlsplit(url)
    path = parsed.path
    patterns = (
        r"/jobs/detail/[^/]+/([0-9a-fA-F-]{36})",
        r"/position/([0-9]+)(?:/detail)?",
        r"/positions/([0-9]+)",
        r"/campus/view/([0-9]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, path)
        if match:
            return match.group(1)
    query = parse_qs(parsed.query)
    for key in ("postId", "positionId", "jobId", "jobUnionId", "id"):
        if query.get(key):
            return query[key][0]
    match = re.search(r"#/job/([A-Za-z0-9-]+)", parsed.fragment)
    if match:
        return match.group(1)
    return None


def _parse_date(value: str) -> date | None:
    normalized = value.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    normalized = normalized.replace(".", "-")
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return None


def parse_jd(
    content: str,
    *,
    company_key: str,
    official_url: str,
    fallback_title: str | None = None,
) -> ParsedJD:
    text = clean_extracted_text(content)
    sections = _section_lines(text)
    title, title_source = _title_from_text(text, fallback_title)
    department_match = _DEPT_RE.search(text)
    city_match = _CITY_RE.search(text)
    date_match = _DATE_RE.search(text)
    if not date_match:
        date_match = re.search(
            r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\s*(?:发布|更新)",
            text[:2_000],
        )
    job_type: str | None = None
    closed = any(
        phrase in text for phrase in ("职位已下架", "职位已关闭", "该职位已下线", "已停止招聘")
    )
    for raw, normalized in (
        ("实习", "internship"),
        ("校招", "campus"),
        ("校园招聘", "campus"),
        ("社招", "full_time"),
        ("社会招聘", "full_time"),
    ):
        if raw in text[:2_000]:
            job_type = normalized
            break

    location = city_match.group(1).strip() if city_match else None
    if location is None:
        for city in _CITY_WORDS:
            if city in text[:2_000]:
                location = city
                break

    responsibilities = sections["responsibilities"]
    requirements = sections["requirements"]
    skills = sections["skills"]
    description = text[:20_000]
    incomplete: list[str] = []
    if not title:
        incomplete.append("缺少明确职位名称")
    if not (responsibilities or requirements):
        incomplete.append("未识别到岗位职责或任职要求")
    if len(text) < 200:
        incomplete.append("提取正文过短")
    if len("\n".join(responsibilities + requirements)) < 80:
        incomplete.append("职责/要求内容不足")
    if len(text) >= 500 and not responsibilities:
        incomplete.append("缺少岗位职责段落")
    if closed:
        incomplete.append("官网页面显示职位已下架/关闭")
    complete = not incomplete

    confidence = 0.35
    if title_source == "extracted":
        confidence += 0.2
    if responsibilities:
        confidence += 0.2
    if requirements:
        confidence += 0.15
    if complete:
        confidence += 0.1
    field_sources = {
        "company": "config",
        "title": title_source,
        "official_url": "configured_url",
        "official_job_id": "url_derived" if _id_from_url(official_url) else "missing",
        "department": "extracted" if department_match else "missing",
        "location": "extracted" if city_match else "inferred_city" if location else "missing",
        "job_type": "extracted" if job_type else "missing",
        "published_date": "extracted" if date_match else "missing",
        "responsibilities": "extracted" if responsibilities else "missing",
        "requirements": "extracted" if requirements else "missing",
        "skills": "extracted" if skills else "missing",
    }
    return ParsedJD(
        company=company_key,
        title=title,
        official_url=official_url,
        department=department_match.group(1).strip() if department_match else None,
        location=location,
        job_type=job_type,
        responsibilities=responsibilities[:50],
        requirements=requirements[:50],
        skills=skills[:50],
        description=description,
        published_date=_parse_date(date_match.group(1)) if date_match else None,
        official_job_id=_id_from_url(official_url),
        field_sources=field_sources,
        confidence=round(min(confidence, 0.99), 2),
        is_complete=complete,
        is_open=not closed,
        incomplete_reasons=incomplete,
        raw_content=text,
    )


def parsed_jd_to_datetime(value: date | None) -> datetime | None:
    return datetime(value.year, value.month, value.day, tzinfo=UTC) if value else None
