"""Storage abstraction for uploaded resume files.

The local implementation is used in development; a production deployment can
swap in S3/MinIO without touching resume services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    size: int
    content_type: str


class FileStorage(Protocol):
    """Minimal object-storage contract used by the resume pipeline."""

    def save(self, *, storage_key: str, content: bytes, content_type: str) -> StoredFile: ...

    def read(self, storage_key: str) -> bytes: ...

    def delete(self, storage_key: str) -> bool: ...

    def exists(self, storage_key: str) -> bool: ...
