"""Candidate profile and preference contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

# Empty entries are accepted then dropped by the service, matching handwritten
# form input; non-empty skills are capped at 50 characters.
Skill = Annotated[str, StringConstraints(max_length=50, strip_whitespace=True)]
JobTypeValue = Literal["internship", "campus", "full_time", "part_time", "contract", "unknown"]
ExperienceKind = Literal[
    "internship", "project", "research", "competition", "open_source", "work", "other"
]


class EducationItem(BaseModel):
    school: str | None = Field(default=None, max_length=200)
    degree: str | None = Field(default=None, max_length=50)
    major: str | None = Field(default=None, max_length=100)
    start_year: int | None = Field(default=None, ge=1950, le=2100)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)


class ProjectItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)


class ExperienceItem(BaseModel):
    kind: ExperienceKind = "other"
    title: str | None = Field(default=None, max_length=200)
    time_range: str | None = Field(default=None, max_length=100)
    skills: list[Skill] = Field(default_factory=list, max_length=50)
    description: str | None = Field(default=None, max_length=2000)


class JobPreferences(BaseModel):
    cities: list[Annotated[str, StringConstraints(max_length=50)]] = Field(
        default_factory=list, max_length=20
    )
    job_types: list[JobTypeValue] = Field(default_factory=list, max_length=6)
    keywords: list[Annotated[str, StringConstraints(max_length=50)]] = Field(
        default_factory=list, max_length=30
    )
    excluded_keywords: list[Annotated[str, StringConstraints(max_length=50)]] = Field(
        default_factory=list, max_length=30
    )
    target_companies: list[Annotated[str, StringConstraints(max_length=100)]] = Field(
        default_factory=list, max_length=20
    )
    target_roles: list[Annotated[str, StringConstraints(max_length=50)]] = Field(
        default_factory=list, max_length=20
    )
    available_start_date: str | None = Field(default=None, max_length=32)
    internship_duration_months: int | None = Field(default=None, ge=1, le=24)
    internship_days_per_week: int | None = Field(default=None, ge=1, le=7)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    remote_ok: bool | None = None


class ProfileRead(BaseModel):
    headline: str | None
    education: list[EducationItem]
    skills: list[str]
    experiences: list[ExperienceItem]
    projects: list[ProjectItem]
    preferences: JobPreferences
    version: int
    verified_by_user: bool
    confirmed_at: datetime | None
    updated_at: datetime | None


class ProfileUpdate(BaseModel):
    headline: str | None = Field(default=None, max_length=200)
    education: list[EducationItem] | None = Field(default=None, max_length=10)
    skills: list[Skill] | None = Field(default=None, max_length=50)
    experiences: list[ExperienceItem] | None = Field(default=None, max_length=30)
    projects: list[ProjectItem] | None = Field(default=None, max_length=20)
    preferences: JobPreferences | None = None
    verified_by_user: bool | None = None

    @model_validator(mode="after")
    def _require_a_change(self) -> ProfileUpdate:
        if not self.model_fields_set:
            raise ValueError("至少需要提交一个待更新字段")
        return self


class ApplyResumeRequest(BaseModel):
    resume_id: UUID
