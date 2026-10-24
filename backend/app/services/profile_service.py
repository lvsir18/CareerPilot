"""Profile and preference domain service."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.text import normalize_string_list
from app.db.models.profile import CandidateProfile, JobPreference
from app.db.models.resume import Resume
from app.db.models.user import User
from app.repositories.profiles import ProfileRepository
from app.schemas.profile import (
    EducationItem,
    ExperienceItem,
    JobPreferences,
    ProfileRead,
    ProfileUpdate,
    ProjectItem,
)


def _preferences_dict(preferences: JobPreference | None) -> dict:
    return {
        "cities": list(preferences.cities_json) if preferences else [],
        "job_types": list(preferences.job_types_json) if preferences else [],
        "keywords": list(preferences.keywords_json) if preferences else [],
        "excluded_keywords": list(preferences.excluded_keywords_json) if preferences else [],
        "target_companies": list(preferences.target_companies_json) if preferences else [],
        "target_roles": list(preferences.target_roles_json) if preferences else [],
    }


def compute_profile_hash(
    profile: CandidateProfile | None,
    preferences: JobPreference | None,
) -> str:
    material = json.dumps(
        {
            "headline": profile.headline if profile else None,
            "skills": profile.skills_json if profile else [],
            "education": profile.education_json if profile else [],
            "experiences": profile.experiences_json if profile else [],
            "projects": profile.projects_json if profile else [],
            "preferences": _preferences_dict(preferences),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ProfileService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = ProfileRepository(session)

    def _serialize(
        self,
        user_id: UUID,
        profile: CandidateProfile | None,
        preferences: JobPreference | None,
    ) -> ProfileRead:
        pref = preferences
        return ProfileRead(
            user_id=user_id,
            headline=profile.headline if profile else None,
            education=[
                EducationItem.model_validate(item)
                for item in (profile.education_json if profile else [])
            ],
            skills=list(profile.skills_json) if profile else [],
            experiences=[
                ExperienceItem.model_validate(item)
                for item in (profile.experiences_json if profile else [])
            ],
            projects=[
                ProjectItem.model_validate(item)
                for item in (profile.projects_json if profile else [])
            ],
            preferences=JobPreferences(
                cities=list(pref.cities_json) if pref else [],
                job_types=list(pref.job_types_json) if pref else [],
                keywords=list(pref.keywords_json) if pref else [],
                excluded_keywords=list(pref.excluded_keywords_json) if pref else [],
                target_companies=list(pref.target_companies_json) if pref else [],
                target_roles=list(pref.target_roles_json) if pref else [],
                available_start_date=pref.available_start_date if pref else None,
                internship_duration_months=pref.internship_duration_months if pref else None,
                internship_days_per_week=pref.internship_days_per_week if pref else None,
                graduation_year=pref.graduation_year if pref else None,
                remote_ok=pref.remote_ok if pref else None,
            ),
            version=profile.version if profile else 0,
            verified_by_user=profile.verified_by_user if profile else False,
            confirmed_at=profile.confirmed_at if profile else None,
            updated_at=profile.updated_at if profile else None,
        )

    def get(self, user: User) -> ProfileRead:
        return self._serialize(
            user.id,
            self._repository.get_profile(user.id),
            self._repository.get_preferences(user.id),
        )

    def _get_or_create_profile(self, user: User) -> CandidateProfile:
        profile = self._repository.get_profile(user.id)
        if profile is None:
            profile = CandidateProfile(
                user_id=user.id,
                skills_json=[],
                education_json=[],
                experiences_json=[],
                projects_json=[],
                version=0,
                verified_by_user=False,
            )
            self._repository.add(profile)
            self._session.flush()
        return profile

    def _get_or_create_preferences(self, user: User) -> JobPreference:
        preferences = self._repository.get_preferences(user.id)
        if preferences is None:
            preferences = JobPreference(
                user_id=user.id,
                cities_json=[],
                job_types_json=[],
                keywords_json=[],
                excluded_keywords_json=[],
                target_companies_json=[],
                target_roles_json=[],
            )
            self._repository.add(preferences)
            self._session.flush()
        return preferences

    def update(self, user: User, payload: ProfileUpdate) -> ProfileRead:
        fields = payload.model_fields_set
        profile = self._get_or_create_profile(user)

        if "headline" in fields:
            profile.headline = payload.headline
        if "education" in fields:
            profile.education_json = [item.model_dump() for item in (payload.education or [])]
        if "skills" in fields:
            profile.skills_json = normalize_string_list(
                payload.skills or [], max_items=50, max_length=50
            )
        if "experiences" in fields:
            profile.experiences_json = [item.model_dump() for item in (payload.experiences or [])]
        if "projects" in fields:
            profile.projects_json = [item.model_dump() for item in (payload.projects or [])]
        if "verified_by_user" in fields:
            profile.verified_by_user = bool(payload.verified_by_user)
            profile.confirmed_at = datetime.now(UTC) if profile.verified_by_user else None

        if "preferences" in fields and payload.preferences is not None:
            preferences = self._get_or_create_preferences(user)
            incoming = payload.preferences
            preferences.cities_json = normalize_string_list(
                incoming.cities, max_items=20, max_length=50
            )
            preferences.job_types_json = normalize_string_list(
                incoming.job_types, max_items=6, max_length=32
            )
            preferences.keywords_json = normalize_string_list(
                incoming.keywords, max_items=30, max_length=50
            )
            preferences.excluded_keywords_json = normalize_string_list(
                incoming.excluded_keywords, max_items=30, max_length=50
            )
            preferences.target_companies_json = normalize_string_list(
                incoming.target_companies, max_items=20, max_length=100
            )
            preferences.target_roles_json = normalize_string_list(
                incoming.target_roles, max_items=20, max_length=50
            )
            preferences.available_start_date = incoming.available_start_date
            preferences.internship_duration_months = incoming.internship_duration_months
            preferences.internship_days_per_week = incoming.internship_days_per_week
            preferences.graduation_year = incoming.graduation_year
            preferences.remote_ok = incoming.remote_ok

        content_hash = compute_profile_hash(profile, self._repository.get_preferences(user.id))
        if (
            "verified_by_user" not in fields
            and profile.verified_by_user
            and content_hash != profile.content_hash
        ):
            # A confirmation only covers the content it was given for. Editing
            # confirmed content must invalidate it, otherwise the UI keeps
            # showing "已确认" for a profile the user never reviewed.
            profile.verified_by_user = False
            profile.confirmed_at = None
        profile.version += 1
        profile.content_hash = content_hash
        self._session.commit()
        self._session.refresh(profile)

        return self._serialize(user.id, profile, self._repository.get_preferences(user.id))

    def confirm(self, user: User) -> ProfileRead:
        profile = self._get_or_create_profile(user)
        preferences = self._repository.get_preferences(user.id)
        profile.verified_by_user = True
        profile.confirmed_at = datetime.now(UTC)
        profile.content_hash = compute_profile_hash(profile, preferences)
        profile.version += 1
        self._session.commit()
        self._session.refresh(profile)
        return self._serialize(user.id, profile, self._repository.get_preferences(user.id))

    def apply_resume(self, user: User, resume: Resume) -> ProfileRead:
        parsed = resume.parsed_json or {}
        profile = self._get_or_create_profile(user)

        education = parsed.get("education") or []
        profile.education_json = [
            EducationItem(
                school=item.get("school"),
                degree=item.get("degree"),
                major=item.get("major"),
                start_year=item.get("start_year"),
                graduation_year=item.get("graduation_year"),
            ).model_dump()
            for item in education
            if isinstance(item, dict)
        ]
        profile.skills_json = normalize_string_list(
            parsed.get("skills") or [], max_items=50, max_length=50
        )
        profile.experiences_json = [
            ExperienceItem(
                kind=item.get("kind", "other"),
                title=item.get("title"),
                time_range=item.get("time_range"),
                skills=item.get("skills") or [],
                description=item.get("description"),
            ).model_dump()
            for item in (parsed.get("experiences") or [])
            if isinstance(item, dict)
        ]
        # Applying a resume is an edit, not a confirmation; the user still has
        # to review and confirm the resulting profile.
        profile.verified_by_user = False
        profile.confirmed_at = None
        profile.version += 1
        profile.content_hash = compute_profile_hash(
            profile, self._repository.get_preferences(user.id)
        )
        self._session.commit()
        self._session.refresh(profile)
        return self._serialize(user.id, profile, self._repository.get_preferences(user.id))
