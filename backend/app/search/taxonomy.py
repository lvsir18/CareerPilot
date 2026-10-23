"""Lightweight, explainable job-family classification.

This is a search filter, not a seniority/skill score. It never invents missing
job details and can always fall back to ``other``.
"""

from __future__ import annotations

JOB_FAMILIES = (
    "llm_agent",
    "algorithm_data",
    "backend",
    "frontend",
    "product",
    "design",
    "operations",
    "other",
)

JOB_FAMILY_LABELS = {
    "llm_agent": "LLM / Agent",
    "algorithm_data": "算法 / 数据",
    "backend": "后端 / 基础架构",
    "frontend": "前端 / 客户端",
    "product": "产品",
    "design": "设计",
    "operations": "运营 / 综合",
    "other": "其他",
}

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "llm_agent",
        (
            "llm",
            "大模型",
            "agent",
            "智能体",
            "aigc",
            "nlp",
            "自然语言",
            "多模态",
            "prompt",
            "rag",
        ),
    ),
    (
        "algorithm_data",
        (
            "算法",
            "机器学习",
            "深度学习",
            "推荐",
            "搜索",
            "广告",
            "数据挖掘",
            "数据分析",
            "数据科学",
            "大数据",
            "数据开发",
            "数据仓库",
            "etl",
            "cv",
            "计算机视觉",
        ),
    ),
    (
        "backend",
        (
            "后端",
            "服务端",
            "基础架构",
            "分布式",
            "java",
            "golang",
            "go语言",
            "c++",
            "python",
            "数据库",
            "中间件",
            "运维",
            "sre",
        ),
    ),
    (
        "frontend",
        (
            "前端",
            "web",
            "react",
            "vue",
            "客户端",
            "android",
            "ios",
            "小程序",
            "跨端",
        ),
    ),
    ("product", ("产品经理", "产品运营", "产品", "pm")),
    ("design", ("设计", "ui", "ux", "视觉", "交互")),
    ("operations", ("运营", "市场", "销售", "招聘", "人力", "hr", "商务", "综合")),
)


def classify_job_family(title: str | None, summary: str | None = None) -> str:
    text = f"{title or ''}\n{summary or ''}".casefold()
    if not text.strip():
        return "other"
    for family, keywords in _RULES:
        if any(keyword.casefold() in text for keyword in keywords):
            return family
    return "other"
