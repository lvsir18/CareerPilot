"""Recruitment email sync, filtering and conflict detection.

Reuses the existing ``.eml`` parser and application matching logic so QQ,
Gmail and manual import share one business pipeline.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.application import Application, ApplicationEvent
from app.db.models.enums import ApplicationStatus
from app.db.models.mailbox import (
    MailboxConnection,
    MailboxSyncCursor,
    MailboxSyncRun,
    RecruitmentEventCandidate,
)
from app.services.application_import_service import ApplicationImportService
from app.services.email_parser import ParsedEmail, parse_eml
from app.services.mailbox_connectors import (
    GmailConnector,
    MailboxError,
    MailboxMessage,
    QQIMAPConnector,
)
from app.services.mailbox_secret import decrypt_secret

logger = logging.getLogger(__name__)

# Strong recruiting signals only. Generic words like "offer"/"application"
# are excluded because marketing and CI mails contain them.
_STRONG_SIGNALS = (
    "招聘",
    "面试",
    "笔试",
    "测评",
    "简历",
    "投递",
    "校招",
    "校园招聘",
    "实习",
    "录用",
    "录取",
    "面试邀请",
    "笔试邀请",
    "面试通知",
    "简历筛选",
    "申请编号",
    "人才招聘",
    "岗位",
    "职位",
    "求职",
    "recruit",
    "interview",
    "assessment",
    "offer letter",
    "job offer",
)

# Senders that are almost always marketing/notification, never recruiting.
_EXCLUDED_SENDERS = (
    "news@",
    "newsletter",
    "marketing@",
    "notifications@",
    "no-reply@github.com",
    "noreply@github.com",
    "steampowered.com",
    "accounts.tencent.com",
)

_GMAIL_QUERY = (
    "newer_than:30d "
    "(招聘 OR 面试 OR 笔试 OR 测评 OR offer OR 简历 OR 投递 OR interview OR assessment)"
)

_CLOSED_STATES = {
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
    ApplicationStatus.CLOSED,
}


class RecruitmentEmailFilter:
    @staticmethod
    def is_recruitment(parsed: ParsedEmail) -> bool:
        haystack = " ".join(
            filter(None, [parsed.subject, parsed.sender, parsed.body_excerpt])
        ).lower()
        if not haystack:
            return False

        sender = (parsed.sender or "").lower()
        hits = sum(1 for keyword in _STRONG_SIGNALS if keyword in haystack)

        # Explicit marketing/notification senders are dropped unless the mail
        # still carries at least two strong recruiting signals.
        if any(marker in sender for marker in _EXCLUDED_SENDERS) and hits < 2:
            return False

        # Two independent signals, or one signal plus a parsed business field.
        return hits >= 2 or (hits >= 1 and bool(parsed.company or parsed.title or parsed.status))


class ConflictDetectionService:
    """Classify how a parsed email relates to an existing application."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._imports = ApplicationImportService(session, settings)

    def match_application(self, user_id: UUID, parsed: ParsedEmail) -> tuple[UUID | None, float]:
        return self._imports._match_application(user_id, parsed)

    def detect(
        self,
        user_id: UUID,
        application_id: UUID | None,
        parsed: ParsedEmail,
    ) -> tuple[str, str | None]:
        if parsed.status is None:
            return "missing_information", "邮件未包含明确的招聘阶段"
        if application_id is None:
            return "ambiguous_match", "无法可靠匹配到已有申请记录"

        application = self._session.get(Application, application_id)
        if application is None or application.user_id != user_id:
            return "ambiguous_match", "申请记录不存在或不属于当前用户"

        events = list(
            self._session.scalars(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == application_id)
                .order_by(ApplicationEvent.event_time.desc().nullslast())
            )
        )
        return self._detect_with_events(application, events, parsed)

    def _detect_with_events(
        self,
        application: Application,
        events: list,
        parsed: ParsedEmail,
    ) -> tuple[str, str | None]:
        if parsed.status is None:
            return "missing_information", "邮件未包含明确的招聘阶段"

        if any(
            event.to_status == parsed.status
            and parsed.event_time is not None
            and event.event_time == parsed.event_time
            for event in events
        ):
            return "duplicate", "已存在同阶段、同时间的进度事件"

        # Compare against the newest known event, falling back to the
        # application confirmation time; an older mail must not roll back the
        # current state.
        latest_time = next(
            (event.event_time for event in events if event.event_time is not None),
            application.last_confirmed_at,
        )
        if (
            parsed.event_time is not None
            and latest_time is not None
            and parsed.event_time < latest_time
            and parsed.status != application.status
        ):
            return (
                "out_of_order",
                "邮件事件时间早于当前状态确认时间，不能自动覆盖当前状态",
            )

        if (
            parsed.status in _CLOSED_STATES
            and application.status in _CLOSED_STATES
            and parsed.status != application.status
        ):
            return "status_conflict", "已结束状态之间互相矛盾，需要人工确认"

        return "none", None


class EmailSyncService:
    def reconcile_stale_runs(self, minutes: int = 10) -> int:
        """Close runs a restarted/crashed worker left in ``running``.

        ``finally`` never executes when the process is killed, so a container
        restart leaves the settings page showing "同步中" forever — which reads
        as "this mailbox stopped working".
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
        stale = self._session.scalars(
            select(MailboxSyncRun).where(
                MailboxSyncRun.status == "running",
                MailboxSyncRun.started_at < cutoff,
            )
        ).all()
        for run in stale:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_summary = (run.error_summary or "任务中断（服务重启或超时）")[:1000]
        if stale:
            self._session.commit()
        return len(stale)

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._filter = RecruitmentEmailFilter()
        self._conflict = ConflictDetectionService(session, settings)
        self._warnings: list[str] = []

    def _cursor(self, connection_id: UUID) -> MailboxSyncCursor:
        cursor = self._session.scalar(
            select(MailboxSyncCursor).where(
                MailboxSyncCursor.connection_id == connection_id,
                MailboxSyncCursor.folder == "INBOX",
            )
        )
        if cursor is None:
            cursor = MailboxSyncCursor(connection_id=connection_id, folder="INBOX")
            self._session.add(cursor)
            self._session.flush()
        return cursor

    def _persist_candidate(
        self,
        connection: MailboxConnection,
        message: MailboxMessage,
        parsed: ParsedEmail,
    ) -> tuple[RecruitmentEventCandidate, bool]:
        existing = self._session.scalar(
            select(RecruitmentEventCandidate).where(
                RecruitmentEventCandidate.user_id == connection.user_id,
                RecruitmentEventCandidate.provider == connection.provider,
                RecruitmentEventCandidate.message_reference == message.message_reference,
            )
        )
        if existing is not None:
            return existing, True

        application_id, match_confidence = self._conflict.match_application(
            connection.user_id, parsed
        )
        conflict_kind, conflict_reason = self._conflict.detect(
            connection.user_id, application_id, parsed
        )
        confidence = min(0.95, max(parsed.confidence, match_confidence * 0.9))
        candidate = RecruitmentEventCandidate(
            user_id=connection.user_id,
            connection_id=connection.id,
            provider=connection.provider,
            message_reference=message.message_reference,
            matched_application_id=application_id,
            parsed_company=parsed.company,
            parsed_title=parsed.title,
            parsed_status=parsed.status.value if parsed.status else None,
            event_time=parsed.event_time,
            scheduled_event_time=parsed.event_time,
            confidence=confidence,
            evidence_summary=parsed.evidence_summary[:2000] if parsed.evidence_summary else None,
            review_status="conflict" if conflict_kind not in {"none"} else "pending",
            conflict_kind=conflict_kind,
            conflict_reason=conflict_reason,
        )
        self._session.add(candidate)
        self._session.flush()
        return candidate, False

    def sync_connection(self, connection: MailboxConnection) -> MailboxSyncRun:
        run = MailboxSyncRun(
            connection_id=connection.id,
            started_at=datetime.now(UTC),
            status="running",
        )
        self._session.add(run)
        self._session.commit()

        scanned = candidates = duplicates = errors = 0
        error_messages: list[str] = []
        self._warnings = []
        try:
            messages = self._fetch_messages(connection)
            scanned = len(messages)
            for message in messages:
                try:
                    parsed = parse_eml(message.raw)
                    if not self._filter.is_recruitment(parsed):
                        continue
                    _candidate, duplicate = self._persist_candidate(connection, message, parsed)
                    if duplicate:
                        duplicates += 1
                    else:
                        candidates += 1
                except Exception as exc:  # per-message isolation
                    errors += 1
                    error_messages.append(str(exc)[:200])
            connection.last_sync_at = datetime.now(UTC)
            connection.last_error = None
            connection.last_success_at = connection.last_sync_at
            run.status = "partial" if (errors or self._warnings) else "success"
        except MailboxError as exc:
            errors += 1
            error_messages.append(exc.message)
            connection.last_error = exc.message[:500]
            connection.status = "error" if exc.code != "GMAIL_TOKEN_EXPIRED" else "expired"
            run.status = "failed"
        finally:
            run.finished_at = datetime.now(UTC)
            run.scanned_count = scanned
            run.candidate_count = candidates
            run.duplicate_count = duplicates
            run.error_count = errors
            summary = error_messages + self._warnings
            run.error_summary = "；".join(summary)[:1000] or None
            self._session.commit()
            self._session.refresh(run)
        return run

    def _fetch_messages(self, connection: MailboxConnection) -> list[MailboxMessage]:
        if not connection.encrypted_secret:
            raise MailboxError("MAILBOX_NOT_CONNECTED", "邮箱凭据不存在，请重新绑定")
        secret = decrypt_secret(self._settings, connection.encrypted_secret)
        cursor = self._cursor(connection.id)

        if connection.provider == "qq_imap":
            connector = QQIMAPConnector(self._settings)
            messages, state = connector.list_messages(
                connection.email_address,
                secret["auth_code"],
                lookback_days=self._settings.mailbox_sync_lookback_days,
                max_messages=self._settings.mailbox_sync_max_messages,
                last_uid=cursor.imap_last_uid,
                expected_uidvalidity=cursor.imap_uidvalidity,
            )
            if state.get("imap_uidvalidity_changed"):
                # Old UIDs are invalid; a bounded re-scan was used instead.
                self._warnings.append(
                    "IMAP UIDVALIDITY 已变化，已按新的代际全量重扫；"
                    "扫描窗口外的历史邮件可能未被覆盖，请按需补充同步"
                )
            cursor.imap_uidvalidity = state.get("imap_uidvalidity")
            cursor.imap_last_uid = state.get("imap_last_uid")
            self._session.commit()
            return messages

        if connection.provider == "gmail":
            connector = GmailConnector(self._settings)
            refreshed = connector.refresh(secret["refresh_token"])
            access_token = refreshed["access_token"]

            if cursor.gmail_history_id:
                history = connector.history(access_token, cursor.gmail_history_id)
                if history is None:
                    # historyId expired: bounded re-scan, then resume increments.
                    ids = connector.list_messages(
                        access_token,
                        query=_GMAIL_QUERY,
                        max_messages=self._settings.mailbox_sync_max_messages,
                    )
                    cursor.gmail_history_id = connector.profile(access_token).get("historyId")
                else:
                    ids = history["message_ids"][: self._settings.mailbox_sync_max_messages]
                    cursor.gmail_history_id = history["history_id"]
            else:
                ids = connector.list_messages(
                    access_token,
                    query=_GMAIL_QUERY,
                    max_messages=self._settings.mailbox_sync_max_messages,
                )
                cursor.gmail_history_id = connector.profile(access_token).get("historyId")

            self._session.commit()
            return [connector.get_message(access_token, message_id) for message_id in ids]
        raise MailboxError("MAILBOX_PROVIDER_UNSUPPORTED", "不支持的邮箱类型")

    def list_candidates(
        self, user_id: UUID, *, review_status: str | None = None, limit: int = 50
    ) -> list[RecruitmentEventCandidate]:
        query = select(RecruitmentEventCandidate).where(
            RecruitmentEventCandidate.user_id == user_id
        )
        if review_status:
            query = query.where(RecruitmentEventCandidate.review_status == review_status)
        query = query.order_by(RecruitmentEventCandidate.created_at.desc()).limit(limit)
        return list(self._session.scalars(query))
