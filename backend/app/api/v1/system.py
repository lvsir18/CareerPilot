"""Runtime metadata used by the dashboard (no secrets are exposed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.schemas.system import SystemInfoResponse

router = APIRouter(tags=["system"])


@router.get(
    "/system/info",
    response_model=SystemInfoResponse,
    summary="当前运行模式与能力开关",
)
def get_system_info(settings: Settings = Depends(get_settings)) -> SystemInfoResponse:
    return SystemInfoResponse(
        app_name=settings.app_name,
        version=__version__,
        app_env=settings.app_env,
        demo_mode=settings.demo_mode,
        execution_mode=settings.execution_mode,
        llm_configured=settings.llm_configured,
        public_connectors_enabled=settings.enable_public_connectors,
        job_sync_enabled=settings.job_sync_enabled,
        api_docs_url=f"{settings.api_base_url.rstrip('/')}/docs",
    )
