"""Extract structured, explainable requirements from a job description.

Required / Preferred / Mentioned are distinguished by the wording around each
skill mention; a technology that merely appears in the JD is never promoted to
a hard requirement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.models.job import Job
from app.services.skill_normalizer import extract_skills

_PREFERRED_MARKERS = (
    "优先",
    "加分",
    "优先考虑",
    "加分项",
    "有经验者优先",
    "熟悉者优先",
    "nice to have",
    "plus",
    "preferred",
    "bonus",
)
_REQUIRED_MARKERS = (
    "要求",
    "必须",
    "精通",
    "熟练掌握",
    "掌握",
    "熟悉",
    "扎实",
    "具备",
    "资格",
    "required",
    "qualification",
    "must",
)

_DEGREE_RE = re.compile(r"(博士|硕士|本科|专科|大专|研究生|本科及以上|硕士及以上|博士及以上)")
_GRADUATION_YEAR_RE = re.compile(r"(20\d{2})\s*届")


@dataclass(slots=True)
class JobFeatures:
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    mentioned_skills: list[str] = field(default_factory=list)
    degree_requirement: str | None = None
    graduation_year_requirement: int | None = None
    job_type: str | None = None
    city: str | None = None


def _jd_text(job: Job) -> str:
    parts = [job.title or "", job.description or ""]
    parts.extend(job.requirements_json or [])
    skills = (job.raw_payload_json or {}).get("skills") or []
    parts.extend(str(item) for item in skills)
    return "\n".join(parts)


def _classify_skills(text: str) -> tuple[list[str], list[str], list[str]]:
    """Classify skills per line so one far-away marker cannot leak across.

    Required takes precedence over Preferred over Mentioned: a skill that is
    both required in one line and preferred elsewhere stays required.
    """
    required: set[str] = set()
    preferred: set[str] = set()
    mentioned: set[str] = set()
    for line in text.splitlines():
        line_skills = extract_skills(line)
        if not line_skills:
            continue
        lowered = line.casefold()
        has_required = any(marker in lowered for marker in _REQUIRED_MARKERS)
        has_preferred = any(marker in lowered for marker in _PREFERRED_MARKERS)
        for skill in line_skills:
            if has_required:
                required.add(skill)
            elif has_preferred:
                preferred.add(skill)
            else:
                mentioned.add(skill)
    preferred -= required
    mentioned -= required | preferred
    return list(required), list(preferred), list(mentioned)


def _extract_degree_requirement(text: str) -> str | None:
    matches = _DEGREE_RE.findall(text)
    if not matches:
        return None
    if any("博士" in item for item in matches):
        return "博士"
    if any("硕士" in item or "研究生" in item for item in matches):
        return "硕士"
    if any("本科" in item for item in matches):
        return "本科"
    if any("专科" in item or "大专" in item for item in matches):
        return "专科"
    return None


def _extract_graduation_year_requirement(text: str) -> int | None:
    match = _GRADUATION_YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def extract_job_features(job: Job) -> JobFeatures:
    text = _jd_text(job)
    required, preferred, mentioned = _classify_skills(text)
    return JobFeatures(
        required_skills=required,
        preferred_skills=preferred,
        mentioned_skills=mentioned,
        degree_requirement=_extract_degree_requirement(text),
        graduation_year_requirement=_extract_graduation_year_requirement(text),
        job_type=job.job_type,
        city=job.city,
    )
