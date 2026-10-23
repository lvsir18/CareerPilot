from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.storage import LocalFileStorage, UnsafeStorageKey


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


def test_save_read_and_delete_roundtrip(storage: LocalFileStorage) -> None:
    stored = storage.save(
        storage_key="resumes/user-a/cv.pdf",
        content=b"%PDF-1.4 fake",
        content_type="application/pdf",
    )

    assert stored.size == 13
    assert storage.exists("resumes/user-a/cv.pdf")
    assert storage.read("resumes/user-a/cv.pdf") == b"%PDF-1.4 fake"

    assert storage.delete("resumes/user-a/cv.pdf") is True
    assert storage.exists("resumes/user-a/cv.pdf") is False
    assert storage.delete("resumes/user-a/cv.pdf") is False


def test_stored_file_is_not_world_readable(storage: LocalFileStorage) -> None:
    storage.save(storage_key="resumes/user-a/cv.pdf", content=b"x", content_type="application/pdf")

    mode = os.stat(storage.root / "resumes/user-a/cv.pdf").st_mode & 0o777
    assert mode == 0o600


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "resumes/../../escape.pdf",
        "",
        "resumes/user a/cv.pdf",
        "resumes\\user\\cv.pdf",
    ],
)
def test_rejects_unsafe_storage_keys(storage: LocalFileStorage, key: str) -> None:
    with pytest.raises(UnsafeStorageKey):
        storage.read(key)


def test_rejects_symlink_escape(storage: LocalFileStorage, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (storage.root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeStorageKey):
        storage.read("link/secret.txt")
