"""Mailbox connection, sync and recruitment candidate endpoints."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.enums import (
    ApplicationSourceType,
    ApplicationStatus,
    EventVerificationStatus,
)
from app.db.models.mailbox import (
    MailboxConnection,
    MailboxSyncRun,
    RecruitmentEventCandidate,
)
from app.schemas.common import DataResponse
from app.schemas.mailbox import (
    CandidateConfirmRequest,
    GmailAuthorizeRead,
    MailboxRead,
    MailboxSyncRunRead,
    MailboxUpdate,
    QQConnectRequest,
    RecruitmentCandidateRead,
    candidate_to_read,
    mailbox_to_read,
)
from app.security.csrf import require_csrf
from app.services.application_service import ApplicationService
from app.services.email_sync_service import EmailSyncService
from app.services.mailbox_connectors import GmailConnector, QQIMAPConnector
from app.services.mailbox_secret import decrypt_secret, encrypt_secret

router = APIRouter(tags=["mailboxes"], dependencies=[Depends(require_csrf)])


def _connection(session: DbSession, user: CurrentUser, mailbox_id: UUID) -> MailboxConnection:
    row = session.scalar(
        select(MailboxConnection).where(
            MailboxConnection.id == mailbox_id, MailboxConnection.user_id == user.id
        )
    )
    if row is None:
        raise AppError(code="MAILBOX_NOT_FOUND", message="邮箱连接不存在", status_code=404)
    return row


def _state_fernet(settings: Settings) -> Fernet:
    if not settings.mailbox_secret_key:
        raise AppError(
            code="MAILBOX_SECRET_UNAVAILABLE",
            message="未配置 MAILBOX_SECRET_KEY，无法启用 Gmail OAuth",
            status_code=503,
        )
    return Fernet(settings.mailbox_secret_key.encode("utf-8"))


@router.get("/mailboxes", response_model=DataResponse[list[MailboxRead]])
def list_mailboxes(session: DbSession, user: CurrentUser) -> DataResponse[list[MailboxRead]]:
    rows = session.scalars(
        select(MailboxConnection)
        .where(MailboxConnection.user_id == user.id)
        .order_by(MailboxConnection.created_at.desc())
    ).all()
    return DataResponse(data=[mailbox_to_read(row) for row in rows])


@router.post("/mailboxes/qq/connect", response_model=DataResponse[MailboxRead], status_code=201)
def connect_qq(
    payload: QQConnectRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[MailboxRead]:
    QQIMAPConnector(settings).test_connection(payload.email_address, payload.auth_code)
    existing = session.scalar(
        select(MailboxConnection).where(
            MailboxConnection.user_id == user.id,
            MailboxConnection.provider == "qq_imap",
            MailboxConnection.email_address == payload.email_address,
        )
    )
    connection = existing or MailboxConnection(
        user_id=user.id, provider="qq_imap", email_address=payload.email_address
    )
    connection.encrypted_secret = encrypt_secret(settings, {"auth_code": payload.auth_code})
    connection.status = "active"
    connection.sync_enabled = True
    connection.last_error = None
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return DataResponse(data=mailbox_to_read(connection))


@router.get("/mailboxes/gmail/authorize", response_model=DataResponse[GmailAuthorizeRead])
def gmail_authorize(settings: AppSettings, user: CurrentUser) -> DataResponse[GmailAuthorizeRead]:
    connector = GmailConnector(settings)
    if not connector.configured:
        return DataResponse(
            data=GmailAuthorizeRead(
                configured=False,
                authorize_url=None,
                message="服务端未配置 Google OAuth（GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI）",
            )
        )
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    state = (
        _state_fernet(settings)
        .encrypt(json.dumps({"u": str(user.id), "v": verifier}).encode("utf-8"))
        .decode("utf-8")
    )
    return DataResponse(
        data=GmailAuthorizeRead(
            configured=True,
            authorize_url=connector.authorize_url(state, challenge),
            message="请前往 Google 完成授权",
        )
    )


@router.get("/mailboxes/gmail/callback", include_in_schema=False)
def gmail_callback(
    code: str,
    state: str,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> RedirectResponse:
    """Browser redirect target; always lands back on the settings page."""
    base = settings.frontend_base_url.rstrip("/")
    try:
        payload = json.loads(_state_fernet(settings).decrypt(state.encode("utf-8")))
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return RedirectResponse(f"{base}/settings/email?gmail=error&reason=state")
    if payload.get("u") != str(user.id):
        return RedirectResponse(f"{base}/settings/email?gmail=error&reason=user")

    connector = GmailConnector(settings)
    tokens = connector.exchange_code(code, payload["v"])
    access_token = tokens["access_token"]
    profile = connector.profile(access_token)
    email_address = profile.get("emailAddress")

    connection = session.scalar(
        select(MailboxConnection).where(
            MailboxConnection.user_id == user.id,
            MailboxConnection.provider == "gmail",
            MailboxConnection.email_address == email_address,
        )
    )
    connection = connection or MailboxConnection(
        user_id=user.id, provider="gmail", email_address=email_address
    )
    connection.encrypted_secret = encrypt_secret(
        settings,
        {
            "refresh_token": tokens.get("refresh_token"),
            "access_token": access_token,
        },
    )
    connection.status = "active"
    connection.sync_enabled = True
    connection.last_error = None
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return RedirectResponse(f"{base}/settings/email?gmail=connected")


@router.patch("/mailboxes/{mailbox_id}", response_model=DataResponse[MailboxRead])
def update_mailbox(
    mailbox_id: UUID,
    payload: MailboxUpdate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[MailboxRead]:
    connection = _connection(session, user, mailbox_id)
    if payload.sync_enabled is not None:
        connection.sync_enabled = payload.sync_enabled
    session.commit()
    session.refresh(connection)
    return DataResponse(data=mailbox_to_read(connection))


@router.delete("/mailboxes/{mailbox_id}", response_model=DataResponse[dict])
def delete_mailbox(
    mailbox_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[dict]:
    """Stop syncing, drop local credentials, then attempt remote revocation.

    Gmail revocation is reported as successful only when Google confirms it.
    QQ authorization codes must be revoked by the user in QQ Mail settings.
    """
    connection = _connection(session, user, mailbox_id)
    provider = connection.provider
    revoked: bool | None = None
    message = ""

    if connection.encrypted_secret:
        try:
            secret = decrypt_secret(settings, connection.encrypted_secret)
        except Exception:  # undecryptable secret is still removed locally
            secret = {}
        if provider == "gmail":
            token = secret.get("refresh_token") or secret.get("access_token")
            if token:
                try:
                    revoked = GmailConnector(settings).revoke(token)
                    message = (
                        "已在 Google 端撤销授权"
                        if revoked
                        else "Google 未确认撤销，请前往 Google 账号安全页面手动移除"
                    )
                except Exception:
                    revoked = False
                    message = "撤销请求失败，请前往 Google 账号安全页面手动移除"
            else:
                message = "本地未保存可撤销的 Gmail 令牌"
        else:
            message = "已删除本地加密授权码；请前往 QQ 邮箱设置撤销该客户端授权码"
    else:
        message = "该连接没有保存凭据"

    connection.sync_enabled = False
    connection.encrypted_secret = None
    session.delete(connection)
    session.commit()
    return DataResponse(
        data={
            "provider": provider,
            "local_credentials_deleted": True,
            "remote_revoked": revoked,
            "message": message,
        }
    )


@router.post("/mailboxes/{mailbox_id}/test", response_model=DataResponse[MailboxRead])
def test_mailbox(
    mailbox_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[MailboxRead]:
    connection = _connection(session, user, mailbox_id)
    if not connection.encrypted_secret:
        raise AppError(code="MAILBOX_NOT_CONNECTED", message="邮箱凭据不存在", status_code=400)
    secret = decrypt_secret(settings, connection.encrypted_secret)
    if connection.provider == "qq_imap":
        QQIMAPConnector(settings).test_connection(connection.email_address, secret["auth_code"])
    elif connection.provider == "gmail":
        connector = GmailConnector(settings)
        refreshed = connector.refresh(secret["refresh_token"])
        connector.profile(refreshed["access_token"])
    connection.status = "active"
    connection.last_error = None
    session.commit()
    session.refresh(connection)
    return DataResponse(data=mailbox_to_read(connection))


@router.post("/mailboxes/{mailbox_id}/sync", response_model=DataResponse[MailboxSyncRunRead])
def sync_mailbox(
    mailbox_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[MailboxSyncRunRead]:
    connection = _connection(session, user, mailbox_id)
    run = EmailSyncService(session, settings).sync_connection(connection)
    return DataResponse(
        data=MailboxSyncRunRead(
            id=run.id,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            scanned_count=run.scanned_count,
            candidate_count=run.candidate_count,
            duplicate_count=run.duplicate_count,
            error_count=run.error_count,
            error_summary=run.error_summary,
        )
    )


@router.get(
    "/mailboxes/{mailbox_id}/sync-runs",
    response_model=DataResponse[list[MailboxSyncRunRead]],
)
def list_sync_runs(
    mailbox_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[list[MailboxSyncRunRead]]:
    _connection(session, user, mailbox_id)
    rows = session.scalars(
        select(MailboxSyncRun)
        .where(MailboxSyncRun.connection_id == mailbox_id)
        .order_by(MailboxSyncRun.created_at.desc())
        .limit(20)
    ).all()
    return DataResponse(
        data=[
            MailboxSyncRunRead(
                id=row.id,
                status=row.status,
                started_at=row.started_at,
                finished_at=row.finished_at,
                scanned_count=row.scanned_count,
                candidate_count=row.candidate_count,
                duplicate_count=row.duplicate_count,
                error_count=row.error_count,
                error_summary=row.error_summary,
            )
            for row in rows
        ]
    )


@router.get(
    "/recruitment-email-candidates",
    response_model=DataResponse[list[RecruitmentCandidateRead]],
)
def list_candidates(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
    review_status: str | None = Query(default=None),
) -> DataResponse[list[RecruitmentCandidateRead]]:
    rows = EmailSyncService(session, settings).list_candidates(user.id, review_status=review_status)
    return DataResponse(data=[candidate_to_read(row) for row in rows])


@router.post(
    "/recruitment-email-candidates/{candidate_id}/confirm",
    response_model=DataResponse[RecruitmentCandidateRead],
)
def confirm_candidate(
    candidate_id: UUID,
    payload: CandidateConfirmRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[RecruitmentCandidateRead]:
    candidate = session.scalar(
        select(RecruitmentEventCandidate).where(
            RecruitmentEventCandidate.id == candidate_id,
            RecruitmentEventCandidate.user_id == user.id,
        )
    )
    if candidate is None:
        raise AppError(code="CANDIDATE_NOT_FOUND", message="待确认邮件不存在", status_code=404)

    application_id = payload.application_id or candidate.matched_application_id
    if not application_id:
        raise AppError(
            code="CANDIDATE_NO_APPLICATION", message="请先选择要更新的申请", status_code=422
        )

    if not payload.keep_current:
        raw_status = payload.status or candidate.parsed_status
        if not raw_status:
            raise AppError(
                code="CANDIDATE_NO_STATUS", message="邮件未识别出明确状态", status_code=422
            )
        try:
            status = ApplicationStatus(raw_status)
        except ValueError as exc:
            raise AppError(
                code="CANDIDATE_INVALID_STATUS", message="状态值非法", status_code=422
            ) from exc
        ApplicationService(session, settings).add_event(
            user,
            application_id,
            status=status,
            event_time=payload.event_time or candidate.event_time or datetime.now(UTC),
            note=payload.note,
            evidence_summary=candidate.evidence_summary,
            source_type=ApplicationSourceType.EMAIL_IMPORT,
            source_reference=f"mailbox:{candidate.message_reference}"[:200],
            verification_status=EventVerificationStatus.EMAIL_CONFIRMED,
        )

    candidate.review_status = "confirmed"
    candidate.matched_application_id = application_id
    session.commit()
    session.refresh(candidate)
    return DataResponse(data=candidate_to_read(candidate))


@router.post(
    "/recruitment-email-candidates/{candidate_id}/discard",
    response_model=DataResponse[RecruitmentCandidateRead],
)
def discard_candidate(
    candidate_id: UUID,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[RecruitmentCandidateRead]:
    candidate = session.scalar(
        select(RecruitmentEventCandidate).where(
            RecruitmentEventCandidate.id == candidate_id,
            RecruitmentEventCandidate.user_id == user.id,
        )
    )
    if candidate is None:
        raise AppError(code="CANDIDATE_NOT_FOUND", message="待确认邮件不存在", status_code=404)
    candidate.review_status = "discarded"
    session.commit()
    session.refresh(candidate)
    return DataResponse(data=candidate_to_read(candidate))
