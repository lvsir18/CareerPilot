"""Shared FastAPI dependencies.

Repositories/services are injected here so that endpoints stay thin and each
dependency can be replaced in tests (see ``app.dependency_overrides``).
"""

from __future__ import annotations

from app.core.cache import check_redis
from app.db.session import check_database
from app.services.health_service import HealthService


def get_health_service() -> HealthService:
    return HealthService(database_check=check_database, cache_check=check_redis)
