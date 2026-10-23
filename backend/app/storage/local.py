"""Local filesystem implementation of :class:`FileStorage`.

Keys are relative paths below a configured root; absolute paths and ``..``
segments are rejected so a caller can never read arbitrary files.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path, PurePosixPath

from app.storage.base import StoredFile

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._/-]+$")


class UnsafeStorageKey(ValueError):
    """Raised when a storage key could escape the storage root."""


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, storage_key: str) -> Path:
        if not storage_key or not _SAFE_KEY.match(storage_key):
            raise UnsafeStorageKey(f"invalid storage key: {storage_key!r}")
        relative = PurePosixPath(storage_key)
        if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
            raise UnsafeStorageKey(f"invalid storage key: {storage_key!r}")
        target = (self._root / Path(*relative.parts)).resolve()
        if target != self._root and self._root not in target.parents:
            raise UnsafeStorageKey(f"storage key escapes root: {storage_key!r}")
        return target

    def save(self, *, storage_key: str, content: bytes, content_type: str) -> StoredFile:
        target = self._resolve(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write with restrictive permissions; never expose a partial file.
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

        return StoredFile(storage_key=storage_key, size=len(content), content_type=content_type)

    def read(self, storage_key: str) -> bytes:
        return self._resolve(storage_key).read_bytes()

    def delete(self, storage_key: str) -> bool:
        target = self._resolve(storage_key)
        if not target.exists():
            return False
        target.unlink()
        return True

    def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).exists()
