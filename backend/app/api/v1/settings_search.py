"""Per-account Tavily credentials (the shared key stays with the deployer)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Response, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.core.errors import AppError
from app.schemas.common import DataResponse
from app.schemas.user_search import (
    ConnectionTestResult,
    SearchSettingsRead,
    SearchSettingsUpdate,
)
from app.search.providers import TavilySearchProvider
from app.security.csrf import require_csrf
from app.services.user_search_service import UserSearchSettingsService, shares_server_search_key

router = APIRouter(
    prefix="/settings/search",
    tags=["settings"],
    dependencies=[Depends(require_csrf)],
)


@router.get("", response_model=DataResponse[SearchSettingsRead], summary="我的搜索 API 配置")
def get_search_settings(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[SearchSettingsRead]:
    data = UserSearchSettingsService(session, settings).describe(user.id)
    return DataResponse(data=SearchSettingsRead(**data))


@router.put("", response_model=DataResponse[SearchSettingsRead], summary="保存我的搜索 API 配置")
def update_search_settings(
    payload: SearchSettingsUpdate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[SearchSettingsRead]:
    data = UserSearchSettingsService(session, settings).upsert(user, api_key=payload.api_key)
    return DataResponse(data=SearchSettingsRead(**data))


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="清除我的搜索 API 配置",
)
def delete_search_settings(
    response: Response,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> Response:
    UserSearchSettingsService(session, settings).clear(user.id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/test",
    response_model=DataResponse[ConnectionTestResult],
    summary="测试 Tavily Key 是否可用（会发起一次真实请求）",
)
def test_search_connection(
    payload: SearchSettingsUpdate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ConnectionTestResult]:
    key = (payload.api_key or "").strip()
    target = "我的 Key"
    if not key:
        key = UserSearchSettingsService(session, settings).resolve(user.id) or ""
        target = "已保存的 Key"
    if not key:
        if not shares_server_search_key(settings, user):
            raise AppError(
                "SEARCH_KEY_REQUIRED",
                "尚未配置搜索 Key：请填写你的 Tavily API Key",
                status_code=422,
            )
        key = settings.tavily_api_key or ""
        target = "服务端默认 Key"
    if not key:
        raise AppError(
            "SEARCH_NOT_CONFIGURED",
            "服务端未配置 Tavily Key，请填写你自己的 Key",
            status_code=422,
        )

    provider = TavilySearchProvider(settings, api_key=key)
    started = time.monotonic()
    try:
        provider.search("careerpilot connectivity test", ["jobs.bytedance.com"], 1)
    except Exception as exc:
        raise AppError(
            "SEARCH_TEST_FAILED",
            f"连接失败：{type(exc).__name__}: {exc}"[:300],
            status_code=502,
        ) from exc
    finally:
        provider.close()
    return DataResponse(
        data=ConnectionTestResult(
            ok=True,
            provider="tavily",
            target=target,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    )
