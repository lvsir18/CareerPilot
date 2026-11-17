"""m2r9: point existing JD postings at their detail page

The JD list API returns no detail URL, so every posting was stored with the list
page (``#/jobs``). That made them impossible to re-check. The site is a
hash-routed SPA and each posting lives at ``#/details?id=<publishId>``, which is
exactly what ``source_job_id`` already stores.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIST_PAGE = "https://campus.jd.com/#/jobs"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE jobs
        SET source_url = 'https://campus.jd.com/#/details?id=' || source_job_id
        WHERE source_url = '{_LIST_PAGE}'
          AND source_id IN (SELECT id FROM job_sources WHERE source_type = 'jd_campus')
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE jobs
        SET source_url = '{_LIST_PAGE}'
        WHERE source_url LIKE 'https://campus.jd.com/#/details?id=%'
          AND source_id IN (SELECT id FROM job_sources WHERE source_type = 'jd_campus')
        """
    )
