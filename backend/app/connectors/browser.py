"""Browser companion import contract (reserved; plugin is not implemented).

The future MV3 extension must only read the user's currently opened, rendered
application page after an explicit click, show a preview, and upload only the
fields the user confirms. It must never upload cookies, passwords or tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class BrowserProgressPreview:
    company_name: str | None
    job_title: str | None
    official_url: str | None
    status: str | None
    event_time: datetime | None
    evidence_summary: str | None


class BrowserProgressImporter(Protocol):
    def read_current_page(self, *, user_confirmed: bool) -> BrowserProgressPreview: ...
