"""Mailbox credential encryption helpers.

Thin wrappers over :mod:`app.services.secret_store` so existing call sites keep
their signature while the storage backend stays swappable.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.services.secret_store import SecretStoreError, get_secret_store

__all__ = ["MailboxSecretError", "decrypt_secret", "encrypt_secret"]

# Backwards-compatible alias (older imports used this name).
MailboxSecretError = SecretStoreError


def encrypt_secret(settings: Settings, payload: dict[str, Any]) -> str:
    return get_secret_store(settings).encrypt(payload)


def decrypt_secret(settings: Settings, token: str) -> dict[str, Any]:
    return get_secret_store(settings).decrypt(token)
