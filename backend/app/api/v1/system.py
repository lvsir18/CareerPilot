"""Runtime metadata used by the dashboard (no secrets are exposed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import __version__
from app.auth.dependencies import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.db.models.agent_run import AgentRun
from app.db.models.job_maintenance import JobMaintenanceRun
from app.schemas.common import DataResponse
from app.schemas.system import (
    ActivityResponse,
    AgentActivity,
    JobMaintenanceActivity,
    SystemInfoResponse,
)

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


@router.get(
    "/system/activity",
    response_model=DataResponse[ActivityResponse],
    summary="当前用户正在运行的后台任务（用于导航加载图标）",
)
def get_activity(session: DbSession, user: CurrentUser) -> DataResponse[ActivityResponse]:
    """Long tasks keep running when the user navigates away; the sidebar polls this.

    Only this user's own runs are reported, and only non-terminal states.
    """
    maintenance = session.scalar(
        select(JobMaintenanceRun)
        .where(
            JobMaintenanceRun.user_id == user.id,
            JobMaintenanceRun.status.in_(("queued", "running")),
        )
        .order_by(JobMaintenanceRun.created_at.desc())
        .limit(1)
    )
    agent_run = session.scalar(
        select(AgentRun)
        .where(
            AgentRun.user_id == user.id,
            AgentRun.status.in_(("queued", "running", "waiting_for_user")),
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )
    progress = dict(maintenance.progress_json or {}) if maintenance else {}
    return DataResponse(
        data=ActivityResponse(
            job_maintenance=(
                JobMaintenanceActivity(
                    run_id=maintenance.id,
                    kind=maintenance.kind,
                    status=maintenance.status,
                    total=int(progress.get("total") or 0),
                    processed=int(progress.get("processed") or 0),
                )
                if maintenance
                else None
            ),
            agent=(
                AgentActivity(
                    run_id=agent_run.id,
                    thread_id=agent_run.thread_id,
                    status=agent_run.status,
                )
                if agent_run
                else None
            ),
        )
    )
