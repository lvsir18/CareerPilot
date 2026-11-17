"""Per-user LLM settings contracts (never carries the plaintext key)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LlmSettingsRead(BaseModel):
    configured: bool
    provider: Literal["openai", "anthropic"] | None = None
    base_url: str | None = None
    model: str | None = None
    key_set: bool = False
    # ``sk-ab…9f2c`` — enough to tell keys apart, useless for calling an API.
    masked_key: str | None = None
    server_default_available: bool = False


class LlmSettingsUpdate(BaseModel):
    provider: Literal["openai", "anthropic"] = "openai"
    # Omit to keep the stored key (editing model/base URL only).
    api_key: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=300)
    model: str | None = Field(default=None, max_length=100)
