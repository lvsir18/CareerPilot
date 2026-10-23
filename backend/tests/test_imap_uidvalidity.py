"""QQ IMAP UIDVALIDITY generation handling.

UIDs are only stable inside one UIDVALIDITY generation; a changed generation
must trigger a bounded full re-scan instead of reusing ``last_uid``.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.services.mailbox_connectors import QQIMAPConnector

RAW_EML = """From: hr@bytedance.com
To: user@example.com
Subject: 面试邀请 - 大模型算法实习生
Date: Thu, 22 Oct 2026 10:00:00 +0800
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

邀请您参加面试。
""".encode()


class _FakeIMAP:
    """Minimal imaplib surface used by QQIMAPConnector."""

    def __init__(self, uidvalidity: int | None, uids: list[int]) -> None:
        self.untagged_responses: dict[str, list[bytes]] = {}
        if uidvalidity is not None:
            self.untagged_responses["UIDVALIDITY"] = [str(uidvalidity).encode()]
        self.uids = uids
        self.search_commands: list[str] = []

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        return "OK", [b""]

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        if command == "search":
            self.search_commands.append(" ".join(str(a) for a in args))
            return "OK", [b" ".join(str(uid).encode() for uid in self.uids)]
        if command == "fetch":
            return "OK", [(b"1 (BODY[] {1})", RAW_EML)]
        return "OK", [b""]

    def close(self) -> None:
        return None

    def logout(self) -> None:
        return None


def _connector(monkeypatch: pytest.MonkeyPatch, client: _FakeIMAP) -> QQIMAPConnector:
    settings = Settings(_env_file=None, app_env="test")
    connector = QQIMAPConnector(settings)
    monkeypatch.setattr(connector, "_connect", lambda email, code: client)
    return connector


def test_uidvalidity_is_read_from_select_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeIMAP(uidvalidity=123456, uids=[1])
    connector = _connector(monkeypatch, client)
    assert connector._uidvalidity(client) == 123456  # type: ignore[arg-type]


def test_uidvalidity_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeIMAP(uidvalidity=None, uids=[1])
    assert _connector(monkeypatch, client)._uidvalidity(client) is None  # type: ignore[arg-type]


def test_same_uidvalidity_uses_uid_incremental(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeIMAP(uidvalidity=100, uids=[11, 12])
    connector = _connector(monkeypatch, client)

    _messages, state = connector.list_messages(
        "a@qq.com",
        "code",
        last_uid=10,
        expected_uidvalidity=100,
    )

    assert state["imap_uidvalidity_changed"] is False
    assert any("UID 11" in command for command in client.search_commands)
    assert state["imap_last_uid"] == 12


def test_changed_uidvalidity_forces_full_rescan_and_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeIMAP(uidvalidity=999, uids=[1, 2])
    connector = _connector(monkeypatch, client)

    _messages, state = connector.list_messages(
        "a@qq.com",
        "code",
        last_uid=500,
        expected_uidvalidity=100,
    )

    assert state["imap_uidvalidity_changed"] is True
    # Old UID must not be reused: search falls back to SINCE, not "UID 501:*".
    assert not any("UID 501" in command for command in client.search_commands)
    assert any("SINCE" in command for command in client.search_commands)
    assert state["imap_last_uid"] == 2


def test_first_sync_without_cursor_does_full_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeIMAP(uidvalidity=555, uids=[3])
    connector = _connector(monkeypatch, client)

    _messages, state = connector.list_messages(
        "a@qq.com", "code", last_uid=None, expected_uidvalidity=None
    )

    assert state["imap_uidvalidity_changed"] is False
    assert any("SINCE" in command for command in client.search_commands)
    assert state["imap_last_uid"] == 3
