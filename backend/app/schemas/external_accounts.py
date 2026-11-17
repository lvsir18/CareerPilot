"""External account connection contracts (no raw secrets)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models.enums import ExternalAuthMode, ExternalConnectionStatus
from app.db.models.external_account import ExternalAccountConnection


class ExternalAccountCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=50)
    auth_mode: ExternalAuthMode
    secret_reference: str | None = Field(default=None, max_length=500)
    scopes: list[str] = Field(default_factory=list, max_length=50)
    expires_at: datetime | None = None


class ExternalAccountRead(BaseModel):
    id: UUID
    provider: str
    auth_mode: ExternalAuthMode
    status: ExternalConnectionStatus
    scopes: list[str]
    expires_at: datetime | None
    last_verified_at: datetime | None
    revoked_at: datetime | None
    secret_configured: bool


def connection_to_read(connection: ExternalAccountConnection) -> ExternalAccountRead:
    return ExternalAccountRead(
        id=connection.id,
        provider=connection.provider,
        auth_mode=connection.auth_mode,
        status=connection.status,
        scopes=list(connection.scopes_json or []),
        expires_at=connection.expires_at,
        last_verified_at=connection.last_verified_at,
        revoked_at=connection.revoked_at,
        secret_configured=bool(connection.secret_reference),
    )
