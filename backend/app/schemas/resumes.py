"""Resume upload and parse-result contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.db.models.resume import Resume


class ResumeEducationRead(BaseModel):
    school: str | None = None
    major: str | None = None
    degree: str | None = None
    start_year: int | None = None
    graduation_year: int | None = None


class ResumeExperienceRead(BaseModel):
    kind: str
    title: str | None = None
    time_range: str | None = None
    skills: list[str] = []
    description: str | None = None


class ResumeParsedRead(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    education: list[ResumeEducationRead] = []
    skills: list[str] = []
    experiences: list[ResumeExperienceRead] = []
    text_length: int = 0
    is_scan_like: bool = False
    warnings: list[str] = []


class ResumeRead(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size: int
    parse_status: str
    parsed: ResumeParsedRead
    error: str | None
    is_primary: bool
    created_at: datetime


def resume_to_read(resume: Resume) -> ResumeRead:
    parsed_raw = resume.parsed_json or {}
    return ResumeRead(
        id=resume.id,
        filename=resume.filename,
        content_type=resume.content_type,
        size=resume.size,
        parse_status=resume.parse_status,
        parsed=ResumeParsedRead(
            name=parsed_raw.get("name"),
            email=parsed_raw.get("email"),
            phone=parsed_raw.get("phone"),
            education=[
                ResumeEducationRead(**item)
                for item in parsed_raw.get("education", [])
                if isinstance(item, dict)
            ],
            skills=list(parsed_raw.get("skills", [])),
            experiences=[
                ResumeExperienceRead(**item)
                for item in parsed_raw.get("experiences", [])
                if isinstance(item, dict)
            ],
            text_length=int(parsed_raw.get("text_length", 0)),
            is_scan_like=bool(parsed_raw.get("is_scan_like", False)),
            warnings=list(parsed_raw.get("warnings", [])),
        ),
        error=resume.error,
        is_primary=resume.is_primary,
        created_at=resume.created_at,
    )
