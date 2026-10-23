"""Email integration contract (design only in M2-R2).

No provider is enabled because no OAuth credentials/consent flow has been
verified. Implementations must use provider-specific OAuth scopes, never accept
an email password, and must not send raw messages to an LLM by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class EmailConnectionInfo:
    provider: str
    status: str
    granted_scope: tuple[str, ...]
    connected_at: datetime | None = None
    last_sync_at: datetime | None = None


@dataclass(frozen=True)
class RecruitmentMessage:
    provider_message_id: str
    subject: str | None
    sender: str | None
    received_at: datetime | None
    body_excerpt: str | None


class EmailConnector(Protocol):
    provider: str

    def connect(self, user_id: str, *, redirect_uri: str) -> str: ...

    def disconnect(self, user_id: str) -> None: ...

    def connection_status(self, user_id: str) -> EmailConnectionInfo: ...

    def list_recruitment_messages(
        self, user_id: str, *, limit: int = 20
    ) -> list[RecruitmentMessage]: ...

    def sync_application_events(self, user_id: str) -> list[str]: ...
