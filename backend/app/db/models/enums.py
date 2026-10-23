"""Domain enums persisted as constrained VARCHAR values."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class SavedListType(StrEnum):
    SAVED = "saved"
    TO_APPLY = "to_apply"


class ApplicationStatus(StrEnum):
    SAVED = "saved"
    PLANNED = "planned"
    TO_APPLY = "to_apply"
    PREPARING = "preparing"
    APPLIED = "applied"
    SCREENING = "screening"
    ASSESSMENT = "assessment"
    ONLINE_ASSESSMENT = "online_assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class ApplicationSourceType(StrEnum):
    MANUAL = "manual"
    EMAIL_IMPORT = "email_import"
    OFFICIAL_API = "official_api"
    BROWSER_ASSISTED = "browser_assisted"


class EventVerificationStatus(StrEnum):
    USER_REPORTED = "user_reported"
    EMAIL_CONFIRMED = "email_confirmed"
    WEBSITE_USER_CONFIRMED = "website_user_confirmed"
    OFFICIAL_API = "official_api"
    UNVERIFIED = "unverified"


class ApplicationImportStatus(StrEnum):
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"


# Job types accepted from preferences and filters. Connectors normalize into
# these values in M2; unknown source values must be stored as ``unknown``.
JOB_TYPE_VALUES = (
    "internship",
    "campus",
    "full_time",
    "part_time",
    "contract",
    "unknown",
)


class SyncStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class JobSourceMethod(StrEnum):
    API = "api"
    PUBLIC_PAGE = "public_page"
    SEARCH_DISCOVERY = "search_discovery"
    MANUAL_IMPORT = "manual_import"
    MANUAL_PASTE = "manual_paste"
    FIXTURE = "fixture"
    UNKNOWN = "unknown"


class LeadVerificationStatus(StrEnum):
    SEARCH_SNIPPET_ONLY = "search_snippet_only"
    USER_PROVIDED = "user_provided"
    VERIFIED_OFFICIAL = "verified_official"
    STALE = "stale"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    USER_CONFIRMED = "user_confirmed"
    UNVERIFIED = "unverified"
    STALE = "stale"


class ExternalAuthMode(StrEnum):
    OAUTH = "oauth"
    BROWSER_SESSION = "browser_session"
    MANUAL_IMPORT = "manual_import"


class ExternalConnectionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
