"""PostgreSQL LangGraph checkpointer helpers.

PostgresSaver.from_conn_string is a context manager that owns a connection
pool; callers must use it inside a ``with`` block so the pool is released.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import Settings


def checkpoint_dsn(settings: Settings) -> str:
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def checkpoint_saver(settings: Settings) -> Iterator[PostgresSaver]:
    with PostgresSaver.from_conn_string(checkpoint_dsn(settings)) as saver:
        saver.setup()
        yield saver
