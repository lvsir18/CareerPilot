"""Secret storage abstraction for mailbox credentials.

The local implementation is Fernet (app-level authenticated encryption). A
Vault/KMS-backed implementation can be added behind the same interface without
touching call sites; nothing here claims that such a backend is deployed.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from cryptography.fernet import Fernet, InvalidToken

from app.core.errors import AppError


class SecretStoreError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="MAILBOX_SECRET_UNAVAILABLE",
            message=message,
            status_code=503,
        )


class SecretStore(Protocol):
    """Minimal contract: authenticated encrypt/decrypt of a JSON payload."""

    def encrypt(self, payload: dict[str, Any]) -> str: ...

    def decrypt(self, token: str) -> dict[str, Any]: ...


class FernetSecretStore:
    """App-level encryption. Key comes from the environment, never from git."""

    def __init__(self, key: str | None) -> None:
        if not key:
            raise SecretStoreError(
                "未配置 MAILBOX_SECRET_KEY，不能保存或读取邮箱凭据；请先配置加密密钥"
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise SecretStoreError("MAILBOX_SECRET_KEY 不是合法的 Fernet 密钥") from exc

    def encrypt(self, payload: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps(payload).encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> dict[str, Any]:
        try:
            raw = self._fernet.decrypt(token.encode("utf-8"))
        except InvalidToken as exc:
            raise SecretStoreError("邮箱凭据无法解密，请重新绑定") from exc
        return json.loads(raw.decode("utf-8"))


def get_secret_store(settings: Any) -> SecretStore:
    """Resolve the configured backend.

    Only ``fernet`` exists today. A ``vault``/``kms`` backend would be added
    here together with the key-rotation plan documented in
    ``docs/M5_SECURITY_REVIEW.md``.
    """
    return FernetSecretStore(getattr(settings, "mailbox_secret_key", None))
