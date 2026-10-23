"""Source evidence exposed with leads and verified jobs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SourceEvidenceRead(BaseModel):
    id: UUID
    source_url: str
    evidence_kind: str
    captured_at: datetime
    verification_method: str
    evidence_ref: str | None
    content_hash: str | None
