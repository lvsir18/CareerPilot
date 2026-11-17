"""Import all models so Alembic and metadata discovery see every table."""

from app.db.models.agent_run import AgentRun, AgentRunEvent
from app.db.models.agent_thread import AgentThread
from app.db.models.application import Application, ApplicationEvent
from app.db.models.application_import import ApplicationImport
from app.db.models.enums import (
    ApplicationImportStatus,
    ApplicationSourceType,
    ApplicationStatus,
    EventVerificationStatus,
    ExternalAuthMode,
    ExternalConnectionStatus,
    JobSourceMethod,
    JobStatus,
    LeadVerificationStatus,
    SavedListType,
    SyncStatus,
    VerificationStatus,
)
from app.db.models.external_account import ExternalAccountConnection
from app.db.models.job import Company, Job, JobSource
from app.db.models.job_lead import JobLead, SourceEvidence
from app.db.models.job_maintenance import JobMaintenanceRun
from app.db.models.mailbox import (
    MailboxConnection,
    MailboxSyncCursor,
    MailboxSyncRun,
    RecruitmentEventCandidate,
)
from app.db.models.match_record import MatchRecord
from app.db.models.profile import CandidateProfile, JobPreference
from app.db.models.resume import Resume
from app.db.models.saved_job import SavedJob
from app.db.models.sync_run import SyncRun
from app.db.models.user import User, UserSession
from app.db.models.user_llm import UserLlmSettings
from app.db.models.user_search import UserSearchSettings

__all__ = [
    "AgentRun",
    "AgentRunEvent",
    "AgentThread",
    "Application",
    "ApplicationEvent",
    "ApplicationImport",
    "ApplicationImportStatus",
    "ApplicationSourceType",
    "ApplicationStatus",
    "CandidateProfile",
    "Company",
    "EventVerificationStatus",
    "ExternalAccountConnection",
    "ExternalAuthMode",
    "ExternalConnectionStatus",
    "Job",
    "JobLead",
    "JobMaintenanceRun",
    "JobPreference",
    "JobSource",
    "JobSourceMethod",
    "JobStatus",
    "LeadVerificationStatus",
    "MailboxConnection",
    "MailboxSyncCursor",
    "MailboxSyncRun",
    "MatchRecord",
    "RecruitmentEventCandidate",
    "Resume",
    "SavedJob",
    "SavedListType",
    "SourceEvidence",
    "SyncRun",
    "SyncStatus",
    "User",
    "UserLlmSettings",
    "UserSearchSettings",
    "UserSession",
    "VerificationStatus",
]
