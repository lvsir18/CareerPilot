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
        timeout=30,
        max_retries=1,
    )


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
