"""Shared column types."""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on PostgreSQL, generic JSON elsewhere (e.g. lightweight unit tests).
JSONType = JSON().with_variant(JSONB, "postgresql")


def enum_column(enum_cls: type[Enum], name: str, length: int = 32) -> SAEnum:
    """Persist enum *values* (not member names) in a constrained VARCHAR."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        validate_strings=True,
        create_constraint=False,
        values_callable=lambda members: [str(member.value) for member in members],
    )


def default_list() -> list[Any]:
    return []
