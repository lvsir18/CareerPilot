"""Configurable skill synonym normalization.

Used by both the resume parser (M3.1) and the job feature extractor (M3.4). A
skill is canonicalized only when its alias appears explicitly; a hypernym is
never treated as equivalent to its more specific skills (e.g. PyTorch does not
imply DeepSpeed or Megatron).
"""

from __future__ import annotations

import re

# canonical -> explicit aliases (all compared casefolded after trimming).
# Keep "go" out of the generic alias set: the short token over-matches text.
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    # Programming languages
    "python": ("python",),
    "java": ("java",),
    "golang": ("golang", "go语言", "go 语言"),
    "cpp": ("c++", "cpp"),
    "c": ("c语言",),
    "javascript": ("javascript", "js", "typescript", "ts"),
    "rust": ("rust",),
    "scala": ("scala",),
    "sql": ("sql",),
    "shell": ("shell", "bash"),
    # Deep-learning frameworks / libraries
    "pytorch": ("pytorch", "torch"),
    "tensorflow": ("tensorflow", "tf"),
    "paddlepaddle": ("paddlepaddle", "paddle"),
    "huggingface": ("huggingface", "hugging face", "transformers库"),
    "transformer": ("transformer", "transformers", "attention"),
    "keras": ("keras",),
    # LLM-related
    "llm": ("llm", "大模型", "大语言模型", "large language model", "llms"),
    "nlp": ("nlp", "自然语言处理", "自然语言"),
    "rag": ("rag", "检索增强生成", "检索增强"),
    "lora": ("lora", "low-rank adaptation", "低秩适配"),
    "qlora": ("qlora",),
    "peft": ("peft", "参数高效微调"),
    "sft": ("sft", "监督微调", "supervised fine-tuning"),
    "rlhf": ("rlhf", "人类反馈强化学习"),
    "dpo": ("dpo", "direct preference optimization"),
    "prompt_engineering": ("prompt", "提示工程", "prompt engineering"),
    "multimodal": ("多模态", "multimodal"),
    "embedding": ("embedding", "向量", "向量检索", "向量数据库"),
    # Agent-related
    "agent": ("agent", "智能体", "ai agent", "multi-agent", "多智能体"),
    "langchain": ("langchain",),
    "langgraph": ("langgraph",),
    "tool_calling": ("tool calling", "工具调用", "function calling", "函数调用"),
    # Recommendation / search / ML domains
    "recommendation": ("推荐算法", "推荐系统", "推荐", "recommendation"),
    "search_algorithm": ("搜索算法", "信息检索", "search algorithm", "检索"),
    "computer_vision": ("cv", "计算机视觉", "computer vision"),
    "speech": ("语音", "asr", "tts", "语音识别", "语音合成"),
    "machine_learning": ("机器学习", "machine learning", "ml"),
    "deep_learning": ("深度学习", "deep learning"),
    "data_mining": ("数据挖掘", "data mining"),
    "data_analysis": ("数据分析", "data analysis"),
    "reinforcement_learning": ("强化学习", "reinforcement learning", "rl"),
    "graph_learning": ("图学习", "graph learning", "gnn", "图神经网络"),
    # Databases / backend / infra
    "mysql": ("mysql",),
    "postgresql": ("postgresql", "postgres"),
    "redis": ("redis",),
    "mongodb": ("mongodb", "mongo"),
    "elasticsearch": ("elasticsearch", "es"),
    "kafka": ("kafka",),
    "flink": ("flink",),
    "spark": ("spark",),
    "hadoop": ("hadoop",),
    "fastapi": ("fastapi",),
    "flask": ("flask",),
    "django": ("django",),
    "spring": ("spring", "springboot", "spring boot"),
    "grpc": ("grpc",),
    "microservices": ("微服务", "microservices"),
    # Engineering / deployment
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "linux": ("linux",),
    "git": ("git",),
    "ci_cd": ("ci/cd", "cicd", "持续集成", "持续部署"),
    "aws": ("aws",),
    "mlflow": ("mlflow",),
    "wandb": ("wandb",),
    "deepspeed": ("deepspeed",),
    "megatron": ("megatron",),
    "vllm": ("vllm",),
    "tensorrt": ("tensorrt",),
    "triton": ("triton", "triton inference"),
}

# Aliases that must match as a whole word, not as a substring. Short/generic
# tokens (ml, rl, ts, es, go) are excluded from substring scanning to avoid
# false positives inside unrelated English words.
_TOKEN_ONLY_ALIASES = {"c", "go", "ml", "rl", "ts", "es", "js", "tf", "cv", "nlp"}


def _build_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            mapping[alias.casefold()] = canonical
    return mapping


_ALIAS_MAP = _build_alias_map()


def normalize_skill(text: str) -> str | None:
    """Return the canonical skill for a raw skill string, or ``None``."""
    value = text.strip()
    if not value:
        return None
    return _ALIAS_MAP.get(value.casefold())


def extract_skills(text: str) -> list[str]:
    """Extract canonical skills that appear explicitly in ``text``.

    Known aliases are matched either as whole tokens or as substrings, except
    for short/generic tokens that are restricted to whole-word matches.
    """
    lowered = text.casefold()
    found: list[str] = []
    seen: set[str] = set()
    for alias, canonical in sorted(_ALIAS_MAP.items(), key=lambda item: (-len(item[0]), item[0])):
        if canonical in seen:
            continue
        if alias in _TOKEN_ONLY_ALIASES:
            matched = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered)
        else:
            matched = alias in lowered
        if matched:
            seen.add(canonical)
            found.append(canonical)
    return found
