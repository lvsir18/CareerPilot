"""Public website connector contract.

PublicWebsiteConnector is intentionally **single-document oriented**: it parses
one official job page that a user explicitly submitted. It is not a bulk
crawler and must not follow site search pages or pagination automatically.
"""

from __future__ import annotations

from typing import ClassVar, Protocol

from app.connectors.schemas import RawJob


class PublicWebsiteConnector(Protocol):
    source_type: ClassVar[str]
    allowed_hosts: ClassVar[frozenset[str]]

    def validate_url(self, url: str) -> str: ...

    def fetch_job_detail(self, url: str) -> RawJob: ...
