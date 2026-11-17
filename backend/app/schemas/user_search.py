"""Per-user search credential contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchSettingsRead(BaseModel):
    configured: bool
    provider: str | None = None
    key_set: bool = False
    masked_key: str | None = None
    server_default_available: bool = False
    server_default_admins_only: bool = True
    provider_enabled: bool = False


class SearchSettingsUpdate(BaseModel):
    # Omit to keep the stored key.
    api_key: str | None = Field(default=None, max_length=200)


class ConnectionTestResult(BaseModel):
    ok: bool
    provider: str
    target: str
    latency_ms: int
    detail: str | None = None
