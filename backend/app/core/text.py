"""Text normalization and safe LIKE helpers."""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_company_name(name: str) -> str:
    """Case/whitespace-insensitive company key used for deduplication."""
    return _WHITESPACE.sub("", name).casefold()


def escape_like(value: str) -> str:
    """Escape user input before embedding it in an ILIKE pattern."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def normalize_string_list(
    values: list[str] | tuple[str, ...],
    *,
    max_items: int,
    max_length: int,
) -> list[str]:
    """Trim, drop empties, de-duplicate case-insensitively, preserve order."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        item = raw.strip()
        if not item:
            continue
        item = item[:max_length]
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= max_items:
            break
    return result
