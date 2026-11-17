"""Unified LLM gateway for the LangGraph agent layer.

A single OpenAI-compatible model (Qwen, DeepSeek, etc.) is used for intent
understanding, tool calling and structured output. API keys never leave the
server process.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.services.user_llm_service import LlmConfig


class LLMNotConfiguredError(RuntimeError):
    """Raised when no usable LLM is configured."""


def build_chat_model(settings: Settings) -> BaseChatModel | None:
    """Return a configured ChatOpenAI model, or None when no key is present."""
    if not settings.llm_configured:
        return None
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        # The summarizer receives every sub-agent answer plus the result list;
        # 30s was not enough once search results were actually included.
        timeout=60,
        max_retries=1,
    )


def build_user_chat_model(config: LlmConfig, settings: Settings) -> BaseChatModel:
    """Build a model from one account's own provider credentials."""
    if config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        extra: dict[str, Any] = {}
        if config.base_url:
            extra["base_url"] = config.base_url
        return ChatAnthropic(
            model=config.model,
            api_key=config.api_key,
            temperature=settings.llm_temperature,
            timeout=60,
            max_retries=1,
            **extra,
        )
    return ChatOpenAI(
        # An OpenAI-compatible gateway (DeepSeek/Qwen) may set its own URL; the
        # user's key alone is not enough without the matching endpoint.
        base_url=config.base_url or settings.llm_base_url,
        api_key=config.api_key,
        model=config.model,
        temperature=settings.llm_temperature,
        timeout=60,
        max_retries=1,
    )


def _is_admin(settings: Settings, user: Any) -> bool:
    email = getattr(user, "email", "") or ""
    return email.strip().lower() in settings.admin_email_set


def resolve_chat_model(session: Any, settings: Settings, user: Any) -> BaseChatModel | None:
    """Per-account key first, then the owner's shared key (admins only)."""
    from app.services.user_llm_service import UserLlmSettingsService

    config = UserLlmSettingsService(session, settings).resolve(user.id)
    if config is not None:
        return build_user_chat_model(config, settings)
    if settings.shared_llm_key_admins_only and not _is_admin(settings, user):
        # A shared key is the deployment owner's quota; other accounts must
        # configure their own instead of silently spending it.
        return None
    return build_chat_model(settings)


def require_chat_model(settings: Settings) -> BaseChatModel:
    model = build_chat_model(settings)
    if model is None:
        raise LLMNotConfiguredError(
            "未配置 LLM（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），无法执行 Agent 任务"
        )
    return model


def supports_tool_calling(model: BaseChatModel | None) -> bool:
    """Best-effort capability probe without making a network call."""
    if model is None:
        return False
    return bool(model.bind_tools and callable(model.bind_tools))


def to_openai_tool(schema: type) -> dict[str, Any]:
    return convert_to_openai_tool(schema)
