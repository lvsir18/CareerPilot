"""m2r8: allow ``rendered_page`` as an evidence verification method

Manually imported links from JS-rendered sites (Alibaba's new campus site) can
only be verified by reading the page in a real browser, which is neither
``public_page_parse`` (Baidu's parser) nor ``tavily_extract``. Recording it
separately keeps the audit trail honest.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = op.f("ck_source_evidence_verification_method_valid")

_OLD = (
    "verification_method IN ('search_provider', 'official_list_page', "
    "'public_page_parse', 'tavily_extract', 'user_confirmed', 'none')"
)
_NEW = (
    "verification_method IN ('search_provider', 'official_list_page', "
    "'public_page_parse', 'tavily_extract', 'rendered_page', 'user_confirmed', 'none')"
)


def upgrade() -> None:
    op.drop_constraint(_NAME, "source_evidence", type_="check")
    op.create_check_constraint(_NAME, "source_evidence", _NEW)


def downgrade() -> None:
    op.drop_constraint(_NAME, "source_evidence", type_="check")
    op.create_check_constraint(_NAME, "source_evidence", _OLD)
