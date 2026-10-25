"""Deterministic PDF/DOCX resume text extraction and rule-based parsing.

This is a conservative extractor: fields that cannot be recognized are left
empty. It never invents skills, experiences, grades or work durations that do
not appear in the source document.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from app.services.skill_normalizer import extract_skills

_MAX_TEXT_LENGTH = 100_000

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

_EDU_DEGREES = ("博士", "硕士", "本科", "学士", "专科", "大专", "高中", "研究生")
_SCHOOL_HINTS = ("大学", "学院", "学校")
_MAJOR_RE = re.compile(r"(?:专业|所学专业|major)\s*[：:]\s*([^\n]{2,40})")
_DEGREE_RE = re.compile(r"(博士|硕士研究生|硕士|本科|学士|专科|大专|高中)(?:学位|学历|在读|毕业)?")
_SCHOOL_RE = re.compile(r"([\u4e00-\u9fa5]{2,30}(?:大学|学院|学校))")
_START_YEAR_RE = re.compile(r"(?:入学|入学时间|开始时间)\s*[：:]?\s*((?:19|20)\d{2})")
_GRADUATION_RE = re.compile(
    r"(?:毕业时间|预计毕业|毕业年份|毕业)\s*[：:]?\s*((?:19|20)\d{2})(?:年|\s|$)?"
)
_GRADUATION_JIE_RE = re.compile(r"((?:19|20)\d{2})\s*年?\s*(?:届|毕业)")
_YEAR_THEN_START_RE = re.compile(r"((?:19|20)\d{2})\s*年?\s*(?:入学|入校|入学时间)")

_SECTION_TITLES = {
    "实习": "internship",
    "工作": "work",
    "项目": "project",
    "科研": "research",
    "竞赛": "competition",
    "获奖": "award",
    "荣誉": "award",
    "奖学金": "award",
    "开源": "open_source",
    "经历": "other",
}
_SECTION_STOP = {"教育", "技能", "专业技能", "自我评价", "语言", "证书", "联系方式"}

# Experience kinds that belong to the profile's "projects" panel.
_PROJECT_KINDS = {"project", "research", "open_source"}
# Kinds kept out of both panels (scholarships, awards, competitions).
_AWARD_KINDS = {"competition", "award"}

# "2025.06 - 2025.09", "2024年6月—2024年9月", "2026.4 - 至今"
# "2025.10", "2025/10", "2025年10月" (a bare year also counts).
_RANGE_PART = r"(?:19|20)\d{2}(?:\s*[./年]?\s*\d{1,2}\s*月?)?"
_RANGE_RE = re.compile(
    rf"({_RANGE_PART})\s*(?:-|–|—|~|至|到)\s*({_RANGE_PART}|至今|今)",
)

_EDU_HEADERS = ("教育背景", "教育经历", "教育", "学历")


def _mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    if len(local) <= 2:
        masked = local[:1] + "*" * (len(local) - 1)
    else:
        masked = local[:2] + "*" * (len(local) - 2)
    return f"{masked}@{domain}"


def _mask_phone(value: str) -> str:
    return f"{value[:3]}****{value[-4:]}"


def extract_text(content: bytes, filename: str) -> str:
    """Extract plain text from a PDF or DOCX byte buffer."""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "pdf":
        return _extract_pdf(content)
    if suffix == "docx":
        return _extract_docx(content)
    raise UnsupportedResumeFormat(f"不支持的简历格式：{suffix or '未知'}")


def _extract_pdf(content: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ResumeParseError("PDF 解析组件不可用") from exc
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            pages = [page.get_text("text") for page in doc]
    except Exception as exc:  # corrupt / encrypted PDF
        raise ResumeParseError("PDF 文件无法解析，可能已损坏或加密") from exc
    text = "\n".join(pages)
    if not text.strip():
        raise EmptyResumeText("PDF 未提取到可识别文本，可能是扫描版")
    return text[:_MAX_TEXT_LENGTH]


def _extract_docx(content: bytes) -> str:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ResumeParseError("DOCX 解析组件不可用") from exc
    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:
        raise ResumeParseError("DOCX 文件无法解析，可能已损坏") from exc
    parts: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text.strip())
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" ".join(cells))
    text = "\n".join(parts)
    if not text.strip():
        raise EmptyResumeText("DOCX 未提取到可识别文本")
    return text[:_MAX_TEXT_LENGTH]


def _parse_education(text: str) -> list[dict]:
    # Only consider the education block when present; otherwise scan the head.
    education_block = text
    for header in _EDU_HEADERS:
        match = re.search(rf"(?:^|\n)\s*{header}[^\n]*\n", text)
        if match:
            education_block = text[match.end() :]
            break
    education_block = education_block.split("技能")[0]
    education_block = education_block.split("经历")[0]

    schools = _SCHOOL_RE.findall(education_block)
    majors = _MAJOR_RE.findall(education_block)
    degrees = _DEGREE_RE.findall(education_block)
    graduation_years = [int(m) for m in _GRADUATION_RE.findall(education_block)] + [
        int(m) for m in _GRADUATION_JIE_RE.findall(education_block)
    ]
    # "2024年入学" is more common than "入学时间：2024"; prefer the former so a
    # later graduation year cannot be misread as the start year.
    start_years = [int(m) for m in _YEAR_THEN_START_RE.findall(education_block)] + [
        int(m) for m in _START_YEAR_RE.findall(education_block)
    ]

    if not (schools or majors or degrees or graduation_years):
        return []

    return [
        {
            "school": schools[0] if schools else None,
            "major": majors[0].strip() if majors else None,
            "degree": degrees[0] if degrees else None,
            "start_year": start_years[0] if start_years else None,
            "graduation_year": graduation_years[0] if graduation_years else None,
        }
    ]


def _looks_like_heading(line: str) -> bool:
    """A section heading is short, has no date and no sentence punctuation."""
    if not line or len(line) > 12:
        return False
    if _RANGE_RE.search(line) or _YEAR_RE.search(line):
        return False
    return not any(mark in line for mark in ("，", "。", "；", ":", "：", "|"))


def _tidy_range_part(part: str) -> str:
    """``2024 12`` / ``2024年12月`` -> ``2024.12``; ``至今`` stays as is."""
    text = re.sub(r"\s+", " ", part).strip()
    match = re.match(r"((?:19|20)\d{2})\s*[./年]?\s*(\d{1,2})\s*月?", text)
    if match:
        return f"{match.group(1)}.{int(match.group(2)):02d}"
    return re.sub(r"\s*[./年]\s*", ".", text).strip(" .")


def _normalise_range(value: str) -> str:
    """Rewrite any date range in the canonical ``2025.10 - 2026.01`` form."""
    match = _RANGE_RE.search(value)
    if not match:
        return re.sub(r"\s+", " ", value).strip()[:100]
    start = _tidy_range_part(match.group(1))
    end = _tidy_range_part(match.group(2))
    return f"{start} - {end}"[:100]


# Marker for "this heading only closes the previous section".
_STOP_KIND = "__stop__"

_BULLET_RE = re.compile(r"^\s*(?:[•·\-\*\u2022]|\d+[.、)])")


def _is_range_anchor(line: str) -> bool:
    """A date range only marks a new entry when it starts the line or is short.

    Descriptions often mention periods ("对比 2024.12-2026.9 的数据"); treating
    those as anchors splits one project into three broken entries.
    """
    if not _RANGE_RE.search(line):
        return False
    stripped = line.lstrip()
    if len(line) > 60:
        return False
    return stripped[:1].isdigit() or len(line) <= 30


def _looks_like_title_tail(line: str) -> bool:
    """The heading of the *next* entry often sits above its date line."""
    text = line.strip()
    if not text or len(text) > 60 or _BULLET_RE.match(text):
        return False
    if _RANGE_RE.search(text):
        return False
    return "。" not in text and text.count("，") <= 1 and "：" not in text


def _split_entries(block: list[str]) -> list[list[str]]:
    """Split one section at real date-range anchors.

    Many resumes put the range on its own line after the title, so an anchor is
    only honoured when the current entry already has one.
    """
    entries: list[list[str]] = []
    current: list[str] = []
    for line in block:
        anchor = _is_range_anchor(line)
        already = any(_is_range_anchor(item) for item in current)
        if anchor and already:
            # The heading of the new entry usually sits just above its date line,
            # possibly after one or two wrapped description lines.
            move_at: int | None = None
            for index in range(len(current) - 1, max(len(current) - 4, -1), -1):
                if _looks_like_title_tail(current[index]):
                    move_at = index
                    break
            if move_at is not None:
                entries.append(current[:move_at])
                current = [*current[move_at:], line]
            else:
                entries.append(current)
                current = [line]
        else:
            current.append(line)
    if current:
        entries.append(current)
    return [entry for entry in entries if any(line.strip() for line in entry)]


def _entry_title(entry: list[str]) -> str | None:
    """Pick the heading line: not a bullet, not a sentence, date removed."""
    fallback: str | None = None
    for line in entry:
        text = _RANGE_RE.sub("", line).strip(" |·-—,，•*")
        if len(text) < 2:
            continue
        if fallback is None and not _BULLET_RE.match(line):
            fallback = text[:200]
        if _BULLET_RE.match(line):
            continue
        if len(text) > 80 or text.count("，") >= 2 or "。" in text:
            continue
        return text[:200]
    return fallback


def _parse_sections(text: str) -> list[dict]:
    """Split the resume into dated entries and label each by its section."""
    lines = [line.strip() for line in text.splitlines()]
    sections: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        if not _looks_like_heading(line):
            continue
        matched = False
        for title, kind in _SECTION_TITLES.items():
            if title in line:
                sections.append((kind, index))
                matched = True
                break
        if matched:
            continue
        # A section that ends the block (教育/技能/…) must still close the
        # previous one, otherwise skills get appended to the last project.
        if any(stop in line for stop in _SECTION_STOP):
            sections.append((_STOP_KIND, index))
    if not sections:
        return []

    items: list[dict] = []
    for position, (kind, start) in enumerate(sections):
        end = sections[position + 1][1] if position + 1 < len(sections) else len(lines)
        if kind == _STOP_KIND:
            continue
        block = [line for line in lines[start + 1 : end] if line]
        # Drop a stray heading that leaked in, but never a body line: matching
        # "语言"/"技能" as substrings used to delete real project titles such as
        # "基于自然语言理解的…".
        block = [
            line
            for line in block
            if not (
                len(line) <= 12
                and not _RANGE_RE.search(line)
                and any(stop in line for stop in _SECTION_STOP)
            )
        ]
        for entry in _split_entries(block):
            title = _entry_title(entry)
            range_line = next((line for line in entry if _RANGE_RE.search(line)), None)
            description = " ".join(entry)
            items.append(
                {
                    "kind": kind,
                    "title": title,
                    "time_range": _normalise_range(range_line) if range_line else None,
                    "skills": extract_skills(description),
                    "description": description[:2000] if description else None,
                }
            )
    return items


def _parse_experiences(text: str) -> list[dict]:
    """Kept for compatibility: every dated entry, regardless of kind."""
    return _parse_sections(text)


@dataclass(slots=True)
class ParsedResume:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    education: list[dict] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    experiences: list[dict] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    awards: list[dict] = field(default_factory=list)
    text_length: int = 0
    is_scan_like: bool = False
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "education": self.education,
            "skills": self.skills,
            "experiences": self.experiences,
            "projects": self.projects,
            "awards": self.awards,
            "text_length": self.text_length,
            "is_scan_like": self.is_scan_like,
            "warnings": self.warnings,
        }


def parse_resume_text(text: str) -> ParsedResume:
    cleaned = text.strip()
    warnings: list[str] = []
    is_scan_like = len(cleaned) < 100
    if is_scan_like:
        warnings.append("文本过短，可能是扫描版或空简历")

    email_match = _EMAIL_RE.search(cleaned)
    phone_match = _PHONE_RE.search(cleaned)
    email = _mask_email(email_match.group(0)) if email_match else None
    phone = _mask_phone(phone_match.group(0)) if phone_match else None

    # Conservative name guess: a short first line that is not a generic header.
    name: str | None = None
    first_line = next((line for line in cleaned.splitlines() if line.strip()), "").strip()
    if 2 <= len(first_line) <= 6 and not re.search(
        r"(简历|resume|cv|求职|应聘|个人)", first_line, re.I
    ):
        name = first_line

    sections = _parse_sections(cleaned)
    experiences = [item for item in sections if item["kind"] not in _PROJECT_KINDS | _AWARD_KINDS]
    projects = [item for item in sections if item["kind"] in _PROJECT_KINDS]
    awards = [item for item in sections if item["kind"] in _AWARD_KINDS]

    return ParsedResume(
        name=name,
        email=email,
        phone=phone,
        education=_parse_education(cleaned),
        skills=extract_skills(cleaned),
        experiences=experiences,
        projects=projects,
        awards=awards,
        text_length=len(cleaned),
        is_scan_like=is_scan_like,
        warnings=warnings,
    )


class ResumeParseError(ValueError):
    """A resume file could not be parsed."""


class EmptyResumeText(ResumeParseError):
    """The document produced no extractable text."""


class UnsupportedResumeFormat(ResumeParseError):
    """The file extension is not PDF or DOCX."""
