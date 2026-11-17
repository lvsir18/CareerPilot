"""Lightweight, explainable job-family classification.

This is a search filter, not a seniority/skill score. It never invents missing
job details and can always fall back to ``other``.

Families are intentionally fine-grained: "算法/数据" and "后端/基础架构" used to
be one bucket each, which made the filter useless when the user only wanted
algorithm roles. Coarse legacy keys are still accepted as groups
(:data:`JOB_FAMILY_GROUPS`) so old bookmarked URLs keep working.
"""

from __future__ import annotations

JOB_FAMILIES = (
    "llm",
    "agent",
    "algorithm",
    "data",
    "backend",
    "infra",
    "frontend",
    "client",
    "test",
    "security",
    "product",
    "design",
    "operations",
    "other",
)

JOB_FAMILY_LABELS = {
    "llm": "大模型 / LLM",
    "agent": "Agent / 应用",
    "algorithm": "算法",
    "data": "数据",
    "backend": "后端",
    "infra": "基础架构 / SRE",
    "frontend": "前端 / Web",
    "client": "客户端",
    "test": "测试 / QA",
    "security": "安全",
    "product": "产品",
    "design": "设计",
    "operations": "运营 / 市场",
    "other": "其他",
}

# Legacy coarse filters kept for compatibility with existing links.
JOB_FAMILY_GROUPS: dict[str, frozenset[str]] = {
    "llm_agent": frozenset({"llm", "agent"}),
    "algorithm_data": frozenset({"algorithm", "data"}),
    # Umbrella for people who just want "AI 岗位": 大模型 / Agent / 算法 一起看。
    "ai": frozenset({"llm", "agent", "algorithm"}),
    # 大厂校招口径的大类：研发 / 工程 合并后端、前端、客户端与基础架构。
    "engineering": frozenset({"backend", "frontend", "client", "infra"}),
    "product_design": frozenset({"product", "design"}),
}

# Ordered: the first hit wins, so put narrow families before broad ones.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "test",
        (
            "测试开发",
            "测试工程师",
            "软件测试",
            "自动化测试",
            "测试专家",
            "quality assurance",
            "qa engineer",
            "sdet",
        ),
    ),
    (
        "security",
        (
            "安全工程师",
            "安全研究",
            "安全攻防",
            "攻防",
            "数据安全",
            "内容安全",
            "渗透",
            "逆向",
            "漏洞",
            "风控",
            "应急响应",
            "security",
        ),
    ),
    (
        "agent",
        (
            "agent",
            "智能体",
            "rag",
            "prompt",
            "langchain",
            "function calling",
            "多智能体",
            "tool use",
        ),
    ),
    (
        "llm",
        (
            "大模型",
            "llm",
            "预训练",
            "微调",
            "fine-tune",
            "aigc",
            "多模态",
            "对话系统",
            "推理优化",
        ),
    ),
    (
        "algorithm",
        (
            "算法",
            "机器学习",
            "深度学习",
            "推荐系统",
            "推荐算法",
            "搜索算法",
            "广告算法",
            "数据挖掘",
            "计算机视觉",
            "cv算法",
            "nlp",
            "自然语言",
            "slam",
            "运筹优化",
        ),
    ),
    (
        "data",
        (
            "数据分析",
            "数据开发",
            "数据仓库",
            "数仓",
            "数据科学",
            "大数据",
            "etl",
            "bi工程",
            "数据治理",
            "指标体系",
        ),
    ),
    (
        "infra",
        (
            "基础架构",
            "分布式",
            "中间件",
            "k8s",
            "kubernetes",
            "运维",
            "sre",
            "dba",
            "稳定性",
            "存储引擎",
            "云原生",
        ),
    ),
    (
        "backend",
        (
            "后端",
            "服务端",
            "java",
            "golang",
            "go语言",
            "c++",
            "数据库",
            "微服务",
            "api",
            "高并发",
        ),
    ),
    (
        "client",
        (
            "客户端",
            "android",
            "ios",
            "flutter",
            "跨端",
            "小程序",
            "鸿蒙",
            "harmonyos",
        ),
    ),
    (
        "frontend",
        ("前端", "web前端", "react", "vue", "h5", "javascript", "typescript"),
    ),
    ("product", ("产品经理", "产品设计", "产品运营", "product manager")),
    ("design", ("设计", "ui设计", "ux", "视觉", "交互设计")),
    (
        "operations",
        ("运营", "市场", "销售", "招聘", "人力", "hr", "商务", "客服", "内容审核", "综合"),
    ),
)


def classify_job_families(title: str | None, summary: str | None = None) -> list[str]:
    """Every family this posting plausibly belongs to.

    A posting is routinely several things at once — "大模型算法工程师" is both
    ``llm`` and ``algorithm``. The old single-label classifier returned the first
    hit while scanning the *JD* too, so one passing mention of 大模型 in the
    description reclassified real algorithm roles and filtering by 算法 showed
    almost nothing.

    Rules:
    - title hits are authoritative and may be multiple;
    - the JD is only consulted when the title says nothing at all, and then only
      the first (narrowest) hit is taken.
    """
    title_text = (title or "").casefold()
    summary_text = (summary or "").casefold()
    matched: list[str] = []
    for family, keywords in _RULES:
        if any(keyword.casefold() in title_text for keyword in keywords):
            matched.append(family)
    if matched:
        return matched
    if not summary_text.strip():
        return ["other"]
    for family, keywords in _RULES:
        if any(keyword.casefold() in summary_text for keyword in keywords):
            return [family]
    return ["other"]


def classify_job_family(title: str | None, summary: str | None = None) -> str:
    """Primary label (first title match, else the JD match, else ``other``)."""
    return classify_job_families(title, summary)[0]


def is_known_family(value: str | None) -> bool:
    """A filter value the API accepts: a fine family or a legacy group."""
    return bool(value) and (value in JOB_FAMILIES or value in JOB_FAMILY_GROUPS)


def job_family_matches(classified: str | list[str], requested: str | None) -> bool:
    """True when any label on the posting satisfies the requested filter."""
    if not requested:
        return True
    labels = [classified] if isinstance(classified, str) else list(classified)
    if requested in JOB_FAMILY_GROUPS:
        return any(label in JOB_FAMILY_GROUPS[requested] for label in labels)
    return requested in labels
