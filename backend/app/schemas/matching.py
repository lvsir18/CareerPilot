"""Job matching and recommendation contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.jobs import JobListItem


class MatchResultRead(BaseModel):
    job_id: UUID | None
    scorer_version: str
    match_level: str
    match_score: int | None
    eligibility_status: str
    eligibility_reasons: list[str] = []
    matched_skills: list[str] = []
    unverified_skills: list[str] = []
    strengths: list[str] = []
    gaps: list[str] = []
    evidence_coverage: float = 0.0
    explanation: str = ""


class RecommendationItem(BaseModel):
    job: JobListItem
    match: MatchResultRead
    saved: bool
    applied_status: str | None
