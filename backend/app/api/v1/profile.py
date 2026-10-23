"""Profile and job preference endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.common import DataResponse
from app.schemas.profile import ApplyResumeRequest, ProfileRead, ProfileUpdate
from app.security.csrf import require_csrf
from app.services.profile_service import ProfileService
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/profile", tags=["profile"], dependencies=[Depends(require_csrf)])


@router.get(
    "/me",
    response_model=DataResponse[ProfileRead],
    summary="读取当前用户的画像与求职偏好",
)
def get_my_profile(session: DbSession, user: CurrentUser) -> DataResponse[ProfileRead]:
    return DataResponse(data=ProfileService(session).get(user))


@router.patch(
    "/me",
    response_model=DataResponse[ProfileRead],
    summary="更新画像/偏好（服务端提升版本号）",
)
def update_my_profile(
    payload: ProfileUpdate,
    session: DbSession,
    user: CurrentUser,
) -> DataResponse[ProfileRead]:
    return DataResponse(data=ProfileService(session).update(user, payload))


@router.post(
    "/confirm",
    response_model=DataResponse[ProfileRead],
    summary="确认正式画像（记录 confirmed_at 与内容哈希）",
)
def confirm_profile(session: DbSession, user: CurrentUser) -> DataResponse[ProfileRead]:
    return DataResponse(data=ProfileService(session).confirm(user))


@router.post(
    "/apply-resume",
    response_model=DataResponse[ProfileRead],
    summary="将某份简历的解析结果应用到画像（仍需用户确认）",
)
def apply_resume(
    payload: ApplyResumeRequest,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ProfileRead]:
    resume = ResumeService(session, settings).get(user, payload.resume_id)
    return DataResponse(data=ProfileService(session).apply_resume(user, resume))
