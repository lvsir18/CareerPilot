"""Email provider connectors (QQ IMAP + Gmail REST API).

Both providers only read messages. QQ uses IMAP with ``BODY.PEEK`` so messages
are never marked as read. Gmail uses the official REST API with the
``gmail.readonly`` scope.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import imaplib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.errors import AppError

_IMAP_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.readonly"


@dataclass(slots=True)
class MailboxMessage:
    provider: str
    provider_message_id: str
    subject: str
    sender: str
    received_at: datetime | None
    raw: bytes

    @property
    def message_reference(self) -> str:
        digest = hashlib.sha256(self.raw).hexdigest()[:32]
        return f"{self.provider}:{self.provider_message_id}:{digest}"


class MailboxError(AppError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(code=code, message=message, status_code=status_code)


def _imap_since(days: int) -> str:
    day = datetime.now(UTC).date() - timedelta(days=days)
    return f"{day.day:02d}-{_IMAP_MONTHS[day.month - 1]}-{day.year}"


class QQIMAPConnector:
    """Fixed host/port; callers cannot inject arbitrary IMAP endpoints."""

    provider = "qq_imap"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _connect(self, email_address: str, auth_code: str) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(self._settings.qq_imap_host, self._settings.qq_imap_port)
        try:
            client.login(email_address, auth_code)
        except imaplib.IMAP4.error as exc:
            client.shutdown()
            raise MailboxError(
                "MAILBOX_AUTH_FAILED",
                "QQ 邮箱授权码无效或 IMAP 未开启，请重新生成授权码",
            ) from exc
        return client

    def test_connection(self, email_address: str, auth_code: str) -> None:
        client = self._connect(email_address, auth_code)
        try:
            client.select("INBOX", readonly=True)
        finally:
            client.logout()

    def list_messages(
        self,
        email_address: str,
        auth_code: str,
        *,
        folder: str = "INBOX",
        lookback_days: int = 30,
        max_messages: int = 200,
        last_uid: int | None = None,
        expected_uidvalidity: int | None = None,
    ) -> tuple[list[MailboxMessage], dict[str, Any]]:
        client = self._connect(email_address, auth_code)
        try:
            status, _ = client.select(folder, readonly=True)
            if status != "OK":
                raise MailboxError("MAILBOX_FOLDER_FAILED", "无法打开指定邮箱文件夹")
            uidvalidity = self._uidvalidity(client)
            # UIDs are only stable within one UIDVALIDITY generation. When the
            # server reports a new generation, the stored last_uid must not be
            # reused; fall back to a bounded full re-scan.
            uidvalidity_changed = (
                expected_uidvalidity is not None
                and uidvalidity is not None
                and uidvalidity != expected_uidvalidity
            )
            incremental = bool(last_uid) and not uidvalidity_changed
            if incremental:
                status, data = client.uid("search", None, f"UID {last_uid + 1}:*")
            else:
                status, data = client.uid("search", None, "SINCE", _imap_since(lookback_days))
            if status != "OK":
                raise MailboxError("MAILBOX_SEARCH_FAILED", "IMAP 搜索邮件失败")
            raw_ids = (data[0] or b"").split()
            uids = [int(item) for item in raw_ids if item.isdigit()]
            if incremental:
                uids = [uid for uid in uids if uid > (last_uid or 0)]
            uids = sorted(uids)[-max_messages:]
            messages: list[MailboxMessage] = []
            for uid in uids:
                status, parts = client.uid("fetch", str(uid), "(BODY.PEEK[])")
                if status != "OK":
                    continue
                payload = _first_payload(parts)
                if not payload:
                    continue
                messages.append(_parse_imap_message(payload, uid, self.provider))
            new_last_uid = uids[-1] if uids else (last_uid if incremental else None)
            return messages, {
                "imap_uidvalidity": uidvalidity,
                "imap_last_uid": new_last_uid,
                "imap_uidvalidity_changed": uidvalidity_changed,
            }
        finally:
            with contextlib.suppress(imaplib.IMAP4.error):
                client.close()
            client.logout()

    @staticmethod
    def _uidvalidity(client: imaplib.IMAP4_SSL) -> int | None:
        """Read the UIDVALIDITY reported by SELECT.

        ``untagged_responses`` holds the raw server response; a UID SEARCH
        would return message ids, not the mailbox generation.
        """
        values = client.untagged_responses.get("UIDVALIDITY")
        if not values:
            return None
        raw = values[0]
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", errors="ignore")
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            return None


def _first_payload(parts: Any) -> bytes | None:
    if not parts:
        return None
    for part in parts:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            return part[1]
    return None


def _parse_imap_message(raw: bytes, uid: int, provider: str) -> MailboxMessage:
    import email
    from email import policy

    message = email.message_from_bytes(raw, policy=policy.default)
    received_at: datetime | None = None
    if message.get("Date"):
        try:
            received_at = parsedate_to_datetime(str(message["Date"]))
        except (TypeError, ValueError):
            received_at = None
    return MailboxMessage(
        provider=provider,
        provider_message_id=str(message.get("Message-ID") or uid),
        subject=str(message.get("Subject") or ""),
        sender=str(message.get("From") or ""),
        received_at=received_at,
        raw=raw,
    )


class GmailConnector:
    provider = "gmail"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.google_client_id
            and self._settings.google_client_secret
            and self._settings.google_oauth_redirect_uri
        )

    def authorize_url(self, state: str, code_challenge: str) -> str:
        if not self.configured:
            raise MailboxError(
                "GMAIL_NOT_CONFIGURED",
                "服务端未配置 Google OAuth，暂时无法绑定 Gmail",
                status_code=503,
            )
        params = {
            "client_id": self._settings.google_client_id,
            "redirect_uri": self._settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": GMAIL_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{GMAIL_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        if not self.configured:
            raise MailboxError("GMAIL_NOT_CONFIGURED", "服务端未配置 Google OAuth", 503)
        response = httpx.post(
            GMAIL_TOKEN_URL,
            data={
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self._settings.google_oauth_redirect_uri,
            },
            timeout=20,
        )
        if response.status_code != 200:
            raise MailboxError("GMAIL_AUTH_FAILED", "Gmail 授权码交换失败", 422)
        return response.json()

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        if not self.configured:
            raise MailboxError("GMAIL_NOT_CONFIGURED", "服务端未配置 Google OAuth", 503)
        response = httpx.post(
            GMAIL_TOKEN_URL,
            data={
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if response.status_code != 200:
            raise MailboxError("GMAIL_TOKEN_EXPIRED", "Gmail 授权已失效，请重新绑定", 401)
        return response.json()

    def profile(self, access_token: str) -> dict[str, Any]:
        response = httpx.get(
            f"{GMAIL_API}/profile",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if response.status_code != 200:
            raise MailboxError("GMAIL_API_FAILED", "读取 Gmail 账户信息失败", 422)
        return response.json()

    def list_messages(
        self,
        access_token: str,
        *,
        query: str = "",
        max_messages: int = 200,
    ) -> list[str]:
        response = httpx.get(
            f"{GMAIL_API}/messages",
            params={"q": query, "maxResults": min(max_messages, 500)},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if response.status_code != 200:
            raise MailboxError("GMAIL_API_FAILED", "Gmail 邮件列表读取失败", 422)
        return [item["id"] for item in response.json().get("messages", [])]

    def revoke(self, token: str) -> bool:
        """Revoke an OAuth token at Google's endpoint.

        Returns True only when Google confirms revocation; deleting local
        ciphertext is not equivalent and must not be reported as such.
        """
        response = httpx.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        return response.status_code == 200

    def history(self, access_token: str, start_history_id: str) -> dict[str, Any] | None:
        """Incremental sync via users.history.list.

        Returns ``None`` when the history id is expired (HTTP 404), so the
        caller can fall back to a bounded re-scan.
        """
        response = httpx.get(
            f"{GMAIL_API}/history",
            params={
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise MailboxError("GMAIL_HISTORY_FAILED", "Gmail 增量同步失败", 422)
        data = response.json()
        message_ids: list[str] = []
        for record in data.get("history", []):
            for added in record.get("messagesAdded", []):
                message = added.get("message", {})
                if message.get("id") and message["id"] not in message_ids:
                    message_ids.append(message["id"])
        return {
            "message_ids": message_ids,
            "history_id": str(data.get("historyId") or start_history_id),
        }

    def get_message(self, access_token: str, message_id: str) -> MailboxMessage:
        response = httpx.get(
            f"{GMAIL_API}/messages/{message_id}",
            params={"format": "raw"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if response.status_code != 200:
            raise MailboxError("GMAIL_API_FAILED", "Gmail 邮件正文读取失败", 422)
        data = response.json()
        raw = base64.urlsafe_b64decode(data["raw"] + "==")
        return _parse_imap_message(raw, 0, self.provider)
