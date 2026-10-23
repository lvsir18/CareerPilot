"""Liveness and readiness endpoints (mounted at the root, not under /api/v1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import get_health_service
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.system import (
    DependencyStatus,
    ErrorResponse,
    HealthResponse,
    ReadinessResponse,
)
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="进程存活检查（不依赖任何外部服务）",
)
def healthz(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        service=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        demo_mode=settings.demo_mode,
    )


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="就绪检查（数据库 / Redis）",
    responses={503: {"model": ErrorResponse, "description": "关键依赖不可用"}},
)
def readyz(health: HealthService = Depends(get_health_service)) -> ReadinessResponse:
    report = health.readiness()
    checks = [
        DependencyStatus(
            name=check.name,
            status="ok" if check.ok else "error",
            detail=check.detail,
        )
        for check in report.checks
    ]
    if not report.ready:
        raise AppError(
            code="DEPENDENCY_UNAVAILABLE",
            message="关键依赖未就绪，请检查数据库与 Redis 连接",
            status_code=503,
            details={"checks": [check.model_dump() for check in checks]},
        )
    return ReadinessResponse(status="ready", checks=checks, checked_at=report.checked_at)
