"""Deterministic heuristic_v1 job matching.

This is an explainable rule scorer, not a learned model. Scores are not
admission probabilities; missing fields never mean "the user fails", and
eligibility is tracked separately from the numeric score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.db.models.job import Job
from app.db.models.job_lead import JobLead
from app.schemas.profile import ProfileRead
from app.search.taxonomy import classify_job_family
from app.services.job_feature_service import JobFeatures, extract_job_features
from app.services.skill_normalizer import normalize_skill

_DEGREE_LEVEL = {"专科": 1, "大专": 1, "本科": 2, "硕士": 3, "博士": 4, "研究生": 3}

# heuristic_v1 initial weights (configurable in future work).
_WEIGHTS = {
    "skill": 0.45,
    "role": 0.25,
    "preference": 0.20,
    "experience": 0.10,
}


@dataclass(slots=True)
class MatchResult:
    job_id: UUID | None
    scorer_version: str
    match_level: str
    match_score: int | None
    eligibility_status: str
    eligibility_reasons: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    unverified_skills: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    evidence_coverage: float = 0.0
    explanation: str = ""

    def as_dict(self) -> dict:
        return {
            "job_id": str(self.job_id) if self.job_id else None,
            "scorer_version": self.scorer_version,
            "match_level": self.match_level,
            "match_score": self.match_score,
            "eligibility_status": self.eligibility_status,
            "eligibility_reasons": self.eligibility_reasons,
            "matched_skills": self.matched_skills,
            "unverified_skills": self.unverified_skills,
            "strengths": self.strengths,
            "gaps": self.gaps,
            "evidence_coverage": self.evidence_coverage,
            "explanation": self.explanation,
        }


class MatchScorer(Protocol):
    version: str

    def score(self, profile: ProfileRead, job: Job) -> MatchResult: ...


class HeuristicV1Scorer:
    version = "heuristic_v1"

    def score(self, profile: ProfileRead, job: Job) -> MatchResult:
        features = extract_job_features(job)
        return self._score_full(profile, job, features)

    def _score_full(
        self,
        profile: ProfileRead,
        job: Job,
        features: JobFeatures,
    ) -> MatchResult:
        user_skills = _normalize_user_skills(profile)
        required = list(features.required_skills)
        preferred = list(features.preferred_skills)

        matched_required = [skill for skill in required if skill in user_skills]
        matched_preferred = [skill for skill in preferred if skill in user_skills]
        matched_mentioned = [skill for skill in features.mentioned_skills if skill in user_skills]
        matched_skills = list(
            dict.fromkeys(matched_required + matched_preferred + matched_mentioned)
        )
        unverified_required = [skill for skill in required if skill not in user_skills]
        unverified_preferred = [skill for skill in preferred if skill not in user_skills]
        # "未体现" ≠ "不会"：a missing preferred skill is still reported as
        # unverified, never as a definitive weakness.
        unverified_skills = unverified_required + unverified_preferred

        skill_score = _skill_score(user_skills, required, preferred, features.mentioned_skills)
        role_score = _role_score(profile, job)
        preference_score = _preference_score(profile, job)
        experience_score = _experience_score(profile, features)

        match_score = round(
            _WEIGHTS["skill"] * skill_score
            + _WEIGHTS["role"] * role_score
            + _WEIGHTS["preference"] * preference_score
            + _WEIGHTS["experience"] * experience_score
        )

        eligibility_status, eligibility_reasons = _eligibility(profile, job, features)

        strengths, gaps = _strengths_and_gaps(
            matched_required,
            matched_preferred,
            matched_mentioned,
            unverified_required,
            unverified_preferred,
        )

        evidence_coverage = _evidence_coverage(features, profile)

        return MatchResult(
            job_id=job.id,
            scorer_version=self.version,
            match_level="full",
            match_score=match_score,
            eligibility_status=eligibility_status,
            eligibility_reasons=eligibility_reasons,
            matched_skills=matched_skills,
            unverified_skills=unverified_skills,
            strengths=strengths,
            gaps=gaps,
            evidence_coverage=evidence_coverage,
            explanation=_explanation(match_score, strengths, gaps, eligibility_status),
        )


def _normalize_user_skills(profile: ProfileRead) -> set[str]:
    skills: set[str] = set()
    for skill in profile.skills:
        canonical = normalize_skill(skill)
        skills.add(canonical if canonical else skill.casefold())
    return skills


def _skill_score(
    user_skills: set[str],
    required: list[str],
    preferred: list[str],
    mentioned: list[str],
) -> int:
    if required:
        matched_required = sum(1 for skill in required if skill in user_skills)
        required_score = matched_required / len(required) * 100
        preferred_bonus = (
            sum(1 for skill in preferred if skill in user_skills) / len(preferred) * 30
            if preferred
            else 0
        )
        return min(100, round(required_score + preferred_bonus))
    if mentioned:
        matched = sum(1 for skill in mentioned if skill in user_skills)
        return round(matched / len(mentioned) * 60)
    return 0


def _role_score(profile: ProfileRead, job: Job) -> int:
    target_roles = {role.casefold() for role in profile.preferences.target_roles}
    if not target_roles:
        return 50
    job_family = classify_job_family(job.title, job.description)
    return 100 if job_family in target_roles else 0


def _preference_score(profile: ProfileRead, job: Job) -> int:
    preferences = profile.preferences
    parts: list[int] = []

    if preferences.cities:
        parts.append(100 if (job.city or "") in preferences.cities else 0)
    else:
        parts.append(50)

    if preferences.job_types:
        parts.append(100 if (job.job_type or "") in preferences.job_types else 0)
    else:
        parts.append(50)

    return round(sum(parts) / len(parts)) if parts else 50


def _experience_score(profile: ProfileRead, features: JobFeatures) -> int:
    experience_skills: set[str] = set()
    for experience in profile.experiences:
        experience_skills.update(skill.casefold() for skill in experience.skills)
    if not profile.experiences:
        return 50
    jd_skills = (
        set(features.required_skills)
        | set(features.preferred_skills)
        | set(features.mentioned_skills)
    )
    if not jd_skills:
        return 50
    overlap = experience_skills & jd_skills
    return round(len(overlap) / len(jd_skills) * 100) if jd_skills else 50


def _eligibility(
    profile: ProfileRead,
    job: Job,
    features: JobFeatures,
) -> tuple[str, list[str]]:
    hard_violations: list[str] = []
    verified: list[str] = []
    missing: list[str] = []

    # Graduation year requirement (e.g. 2027届 campus recruiting).
    if features.graduation_year_requirement is not None:
        user_year = profile.preferences.graduation_year
        if user_year is None:
            missing.append(
                f"岗位要求 {features.graduation_year_requirement} 届，画像未提供毕业年份"
            )
        elif user_year == features.graduation_year_requirement:
            verified.append("毕业年份满足要求")
        else:
            hard_violations.append(
                "毕业年份不满足：岗位要求 "
                f"{features.graduation_year_requirement} 届，画像为 {user_year} 届"
            )

    # Degree requirement.
    if features.degree_requirement is not None:
        user_degree = _highest_degree(profile)
        if user_degree is None:
            missing.append(f"岗位要求 {features.degree_requirement} 学历，画像未提供学历")
        elif _DEGREE_LEVEL.get(user_degree, 0) < _DEGREE_LEVEL.get(features.degree_requirement, 0):
            hard_violations.append(
                f"学历不满足：岗位要求 {features.degree_requirement}，画像为 {user_degree}"
            )
        else:
            verified.append("学历满足要求")

    # Hard job-type constraint.
    if profile.preferences.job_types and job.job_type not in profile.preferences.job_types:
        hard_violations.append(
            f"求职类型不满足：偏好 {profile.preferences.job_types}，岗位为 {job.job_type}"
        )

    if hard_violations:
        return ("ineligible", hard_violations)
    if verified:
        return ("eligible", verified)
    return ("unknown", missing)


def _highest_degree(profile: ProfileRead) -> str | None:
    levels: list[str] = []
    for education in profile.education:
        if education.degree:
            levels.append(education.degree)
    if not levels:
        return None
    return max(levels, key=lambda degree: _DEGREE_LEVEL.get(degree, 0))


def _strengths_and_gaps(
    matched_required: list[str],
    matched_preferred: list[str],
    matched_mentioned: list[str],
    unverified_required: list[str],
    unverified_preferred: list[str],
) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    gaps: list[str] = []
    if matched_required:
        strengths.append("具备岗位要求的主要技能")
    if matched_preferred:
        strengths.append("覆盖部分岗位加分技能")
    if matched_mentioned and not matched_required:
        strengths.append("具备岗位相关技术")
    if unverified_required:
        gaps.append("简历未体现部分必需技能")
    if unverified_preferred:
        gaps.append("部分加分技能未在简历中体现")
    return strengths, gaps


def _evidence_coverage(features: JobFeatures, profile: ProfileRead) -> float:
    # Reflect how much of the score is backed by actual data rather than blanks.
    covered = 0
    total = 0
    if features.required_skills or features.preferred_skills or features.mentioned_skills:
        covered += 1
        total += 1
    else:
        total += 1
    if features.degree_requirement:
        covered += 1
        total += 1
    else:
        total += 1
    if features.graduation_year_requirement:
        covered += 1
        total += 1
    else:
        total += 1
    if profile.skills:
        covered += 1
        total += 1
    else:
        total += 1
    return round(covered / total, 2) if total else 0.0


def _explanation(
    score: int,
    strengths: list[str],
    gaps: list[str],
    eligibility_status: str,
) -> str:
    if eligibility_status == "ineligible":
        return "存在不满足的硬性条件，详见资格说明"
    if not strengths and not gaps:
        return "信息不足，无法给出可靠评分"
    parts = list(strengths + gaps)
    return "；".join(parts[:3])


def basic_match(lead: JobLead) -> MatchResult:
    """A JobLead with only a title/summary gets a relevance label, not a score."""
    return MatchResult(
        job_id=None,
        scorer_version="heuristic_v1",
        match_level="basic",
        match_score=None,
        eligibility_status="unknown",
        explanation="招聘信息不完整，仅提供基础匹配",
        evidence_coverage=0.0,
    )
