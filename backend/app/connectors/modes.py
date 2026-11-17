"""Future connector modes (interfaces only; no unverified auto-login).

These protocols make the extension points explicit without enabling any
provider that has not been reviewed and allow-listed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.connectors.schemas import RawJob


@dataclass(frozen=True)
class AuthorizedConnectionContext:
    """Opaque server-side handle; never contains a password or raw cookie."""

    connection_id: UUID
    user_id: UUID
    provider: str
    auth_mode: str


class AuthorizedSessionConnector(Protocol):
    """Only for providers with written permission for automated access."""

    source_type: str

    def fetch_jobs_with_connection(
        self, context: AuthorizedConnectionContext, source_config: dict[str, Any]
    ) -> list[RawJob]: ...


class SearchDiscoveryConnector(Protocol):
    """Discovery interface; implementations require an approved source policy."""

    source_type: str

    def search(self, query: str, source_config: dict[str, Any]) -> list[RawJob]: ...
