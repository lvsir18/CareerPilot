"""Per-account model credentials, so one server key is not shared by everyone."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Response, status
from langchain_core.messages import HumanMessage

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.core.errors import AppError
from app.schemas.common import DataResponse
from app.schemas.user_llm import LlmSettingsRead, LlmSettingsUpdate
from app.schemas.user_search import ConnectionTestResult
from app.security.csrf import require_csrf
from app.services.user_llm_service import UserLlmSettingsService

router = APIRouter(
    prefix="/settings/llm",
    tags=["settings"],
    dependencies=[Depends(require_csrf)],
)


@router.get("", response_model=DataResponse[LlmSettingsRead], summary="我的模型 API 配置")
def get_llm_settings(
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[LlmSettingsRead]:
    data = UserLlmSettingsService(session, settings).describe(user.id)
    return DataResponse(data=LlmSettingsRead(**data))


@router.put("", response_model=DataResponse[LlmSettingsRead], summary="保存我的模型 API 配置")
def update_llm_settings(
    payload: LlmSettingsUpdate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[LlmSettingsRead]:
    data = UserLlmSettingsService(session, settings).upsert(
        user,
        provider=payload.provider,
        api_key=payload.api_key,
        base_url=payload.base_url,
        model=payload.model,
    )
    return DataResponse(data=LlmSettingsRead(**data))


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="清除我的模型 API 配置（回退到服务端默认）",
)
def delete_llm_settings(
    response: Response,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> Response:
    UserLlmSettingsService(session, settings).clear(user.id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/test",
    response_model=DataResponse[ConnectionTestResult],
    summary="测试模型 Key 是否可用（会发起一次真实请求）",
)
def test_llm_connection(
    payload: LlmSettingsUpdate,
    session: DbSession,
    settings: AppSettings,
    user: CurrentUser,
) -> DataResponse[ConnectionTestResult]:
    from app.agents.llm import _is_admin, build_chat_model, build_user_chat_model
    from app.services.user_llm_service import DEFAULT_MODELS, LlmConfig

    api_key = (payload.api_key or "").strip()
    target = "我的 Key"
    config: LlmConfig | None = None
    if api_key:
        # Test what the user typed before saving it.
        config = LlmConfig(
            provider=payload.provider,
            api_key=api_key,
            base_url=(payload.base_url or "").strip() or None,
            model=(payload.model or "").strip() or DEFAULT_MODELS[payload.provider],
        )
    else:
        config = UserLlmSettingsService(session, settings).resolve(user.id)
        target = "已保存的 Key"

    if config is not None:
        model = build_user_chat_model(config, settings)
        provider = config.provider
    else:
        if settings.shared_llm_key_admins_only and not _is_admin(settings, user):
            raise AppError(
                "LLM_KEY_REQUIRED",
                "尚未配置模型 Key：请填写你自己的 API Key",
                status_code=422,
            )
        model = build_chat_model(settings)
        if model is None:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                "服务端未配置模型，请填写你自己的 API Key",
                status_code=422,
            )
        provider = "server"
        target = "服务端默认 Key"

    started = time.monotonic()
    try:
        reply = model.invoke([HumanMessage(content="ping")])
    except Exception as exc:
        raise AppError(
            "LLM_TEST_FAILED",
            f"连接失败：{type(exc).__name__}: {exc}"[:300],
            status_code=502,
        ) from exc
    return DataResponse(
        data=ConnectionTestResult(
            ok=True,
            provider=provider,
            target=target,
            latency_ms=int((time.monotonic() - started) * 1000),
            detail=str(getattr(reply, "content", ""))[:120],
        )
    )
