"""Registration, login, logout and current-user endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.auth.service import AuthService
from app.auth.session import clear_session_cookie, set_session_cookie
from app.core.errors import AppError
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetRequest,
    RegisterRequest,
    UserRead,
)
from app.schemas.common import DataResponse
from app.security.csrf import (
    clear_csrf_cookie,
    issue_csrf_token,
    require_csrf,
    verify_origin_dependency,
)
from app.security.rate_limit import LoginRateLimiter, get_client_ip, get_login_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class CsrfTokenRead(BaseModel):
    csrf_token: str
    header_name: str


def _rate_limit_error(decision) -> AppError:
    retry_after = decision.retry_after_seconds or 60
    return AppError(
        code="RATE_LIMITED",
        message="尝试过于频繁，请稍后再试",
        status_code=429,
        details={"retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


@router.get(
    "/csrf",
    response_model=DataResponse[CsrfTokenRead],
    summary="获取（并轮换）CSRF Token",
)
def get_csrf_token(
    response: Response,
    settings: AppSettings,
) -> DataResponse[CsrfTokenRead]:
    token = issue_csrf_token(response, settings)
    return DataResponse(data=CsrfTokenRead(csrf_token=token, header_name=settings.csrf_header_name))


@router.post(
    "/register",
    response_model=DataResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    summary="注册并建立登录会话",
    dependencies=[Depends(verify_origin_dependency)],
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
) -> DataResponse[UserRead]:
    decision = limiter.consume(
        "register",
        ip=get_client_ip(request, settings),
        email=str(payload.email),
    )
    if not decision.allowed:
        raise _rate_limit_error(decision)

    user, token = AuthService(session, settings).register(str(payload.email), payload.password)
    limiter.reset_account("register", str(payload.email))
    set_session_cookie(response, token, settings)
    issue_csrf_token(response, settings)
    return DataResponse(data=UserRead.model_validate(user))


@router.post(
    "/login",
    response_model=DataResponse[UserRead],
    summary="登录",
    dependencies=[Depends(verify_origin_dependency)],
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
) -> DataResponse[UserRead]:
    email = str(payload.email)
    decision = limiter.consume(
        "login",
        ip=get_client_ip(request, settings),
        email=email,
    )
    if not decision.allowed:
        raise _rate_limit_error(decision)

    user, token = AuthService(session, settings).login(email, payload.password)
    limiter.reset_account("login", email)
    set_session_cookie(response, token, settings)
    issue_csrf_token(response, settings)
    return DataResponse(data=UserRead.model_validate(user))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="退出并撤销当前会话",
    dependencies=[Depends(require_csrf)],
)
def logout(
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
) -> Response:
    AuthService(session, settings).logout(request.cookies.get(settings.session_cookie_name))
    clear_session_cookie(response, settings)
    clear_csrf_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="修改密码（需要当前密码）",
    dependencies=[Depends(require_csrf)],
)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> Response:
    AuthService(session, settings).change_password(
        user,
        payload.current_password,
        payload.new_password,
        # Keep the caller's own session so changing the password does not log
        # the user out of the tab they are using.
        keep_token=request.cookies.get(settings.session_cookie_name),
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="忘记密码时凭邮箱重置（仅本地个人版开启）",
    dependencies=[Depends(verify_origin_dependency)],
)
def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
) -> Response:
    if not settings.password_reset_enabled:
        raise AppError(
            code="PASSWORD_RESET_DISABLED",
            message="本部署未开启密码重置，请联系管理员或手动修改数据库",
            status_code=403,
        )
    # Same limiter as login: a reset endpoint without throttling is a free
    # account-takeover primitive on a local network.
    decision = limiter.consume(
        "password-reset",
        ip=get_client_ip(request, settings),
        email=str(payload.email),
    )
    if not decision.allowed:
        raise _rate_limit_error(decision)

    AuthService(session, settings).reset_password(str(payload.email), payload.new_password)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/me",
    response_model=DataResponse[UserRead],
    summary="当前登录用户",
)
def me(user: CurrentUser, settings: AppSettings) -> DataResponse[UserRead]:
    data = UserRead.model_validate(user).model_copy(
        update={"is_admin": user.email.strip().lower() in settings.admin_email_set}
    )
    return DataResponse(data=data)
