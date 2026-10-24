"""Versioned job matching and personalized recommendations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.enums import SavedListType, VerificationStatus
from app.db.models.job import Job
from app.db.models.match_record import MatchRecord
from app.db.models.profile import CandidateProfile
from app.db.models.user import User
from app.repositories.applications import ApplicationRepository
from app.repositories.jobs import JobQuery, JobRepository
from app.repositories.match_records import MatchRecordRepository
from app.repositories.profiles import ProfileRepository
from app.repositories.saved_jobs import SavedJobRepository
from app.schemas.jobs import job_to_list_item
from app.schemas.matching import MatchResultRead, RecommendationItem
from app.schemas.profile import ProfileRead
from app.services.job_lead_service import JobLeadService
from app.services.matching_service import HeuristicV1Scorer, MatchResult, basic_match
from app.services.profile_service import ProfileService

_RECOMMENDATION_SCAN_LIMIT = 200


def _result_from_dict(data: dict) -> MatchResult:
    return MatchResult(
        job_id=UUID(data["job_id"]) if data.get("job_id") else None,
        scorer_version=data["scorer_version"],
        match_level=data["match_level"],
        match_score=data.get("match_score"),
        eligibility_status=data["eligibility_status"],
        eligibility_reasons=list(data.get("eligibility_reasons", [])),
        matched_skills=list(data.get("matched_skills", [])),
        unverified_skills=list(data.get("unverified_skills", [])),
        strengths=list(data.get("strengths", [])),
        gaps=list(data.get("gaps", [])),
        evidence_coverage=float(data.get("evidence_coverage", 0.0)),
        explanation=data.get("explanation", ""),
    )


def _result_to_read(result: MatchResult) -> MatchResultRead:
    return MatchResultRead(**result.as_dict())


class RecommendationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._scorer = HeuristicV1Scorer()
        self._matches = MatchRecordRepository(session)
        self._profiles = ProfileRepository(session)
        self._jobs = JobRepository(session)
        self._saved = SavedJobRepository(session)
        self._applications = ApplicationRepository(session)

    def _profile_data(self, user: User) -> tuple[ProfileRead, CandidateProfile | None]:
        row = self._profiles.get_profile(user.id)
        preferences = self._profiles.get_preferences(user.id)
        read = ProfileService(self._session)._serialize(user.id, row, preferences)
        return read, row

    def _confirmed_profile(self, user: User) -> tuple[ProfileRead, CandidateProfile | None]:
        """Single gate for every scoring entry point.

        Scoring a draft profile produced scores the job page then refused to
        show, so both pages must answer the same way: confirm first.
        """
        read, row = self._profile_data(user)
        if not read.verified_by_user:
            raise AppError(
                code="PROFILE_NOT_CONFIRMED",
                message="画像尚未确认：请先在「我的画像」完成确认，再查看匹配与推荐",
                status_code=409,
            )
        return read, row

    def _match_job(
        self,
        user: User,
        profile_read: ProfileRead,
        profile_row: CandidateProfile | None,
        job: Job,
    ) -> MatchResult:
        content_hash = profile_row.content_hash if profile_row else ""
        cached = self._matches.get(
            user_id=user.id,
            job_id=job.id,
            job_lead_id=None,
            profile_version=profile_read.version,
            scorer_version=self._scorer.version,
            job_content_hash=job.content_hash,
        )
        if cached is not None:
            return _result_from_dict(cached.result_json)

        result = self._scorer.score(profile_read, job)
        self._matches.add(
            MatchRecord(
                user_id=user.id,
                job_id=job.id,
                profile_version=profile_read.version,
                profile_content_hash=content_hash,
                job_content_hash=job.content_hash,
                scorer_version=self._scorer.version,
                match_level=result.match_level,
                result_json=result.as_dict(),
            )
        )
        self._session.commit()
        return result

    def _status(self, user: User, job: Job) -> tuple[bool, str | None]:
        saved = self._saved.get(user.id, job.id, SavedListType.SAVED) is not None
        application = self._applications.get_by_job(user.id, job.id)
        return saved, (application.status.value if application else None)

    def match_job(self, user: User, job_id: UUID) -> RecommendationItem:
        job = self._jobs.get(job_id, include_demo=self._settings.demo_mode)
        if job is None:
            raise AppError(code="JOB_NOT_FOUND", message="岗位不存在", status_code=404)
        profile_read, profile_row = self._confirmed_profile(user)
        result = self._match_job(user, profile_read, profile_row, job)
        saved, applied_status = self._status(user, job)
        return RecommendationItem(
            job=job_to_list_item(job),
            match=_result_to_read(result),
            saved=saved,
            applied_status=applied_status,
        )

    def match_lead(self, user: User, lead_id: UUID) -> MatchResultRead:
        lead = JobLeadService(self._session, self._settings).get_for_user(lead_id, user.id)
        return _result_to_read(basic_match(lead))

    def recommendations(
        self,
        user: User,
        *,
        companies: tuple[str, ...] = (),
        cities: tuple[str, ...] = (),
        job_types: tuple[str, ...] = (),
        exclude_applied: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[RecommendationItem], int]:
        profile_read, profile_row = self._confirmed_profile(user)
        jobs, _ = self._jobs.list(
            JobQuery(
                companies=companies,
                cities=cities,
                job_types=job_types,
                include_demo=self._settings.demo_mode,
                sort="first_seen_at_desc",
                page=1,
                page_size=_RECOMMENDATION_SCAN_LIMIT,
                extra_conditions=(Job.verification_status == VerificationStatus.VERIFIED,),
            )
        )

        items: list[RecommendationItem] = []
        for job in jobs:
            saved, applied_status = self._status(user, job)
            if exclude_applied and applied_status is not None:
                continue
            result = self._match_job(user, profile_read, profile_row, job)
            items.append(
                RecommendationItem(
                    job=job_to_list_item(job),
                    match=_result_to_read(result),
                    saved=saved,
                    applied_status=applied_status,
                )
            )

        items.sort(
            key=lambda item: (
                item.match.match_score is None,
                -(item.match.match_score or 0),
            )
        )
        offset = (page - 1) * page_size
        return items[offset : offset + page_size], len(items)
