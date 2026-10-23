from __future__ import annotations

from uuid import uuid4

from app.db.models.job import Job
from app.services.job_feature_service import extract_job_features


def _job(**overrides) -> Job:
    values = {
        "source_id": uuid4(),
        "source_job_id": "jd-test",
        "company_id": uuid4(),
        "title": "大模型算法实习生",
        "content_hash": "hash",
        "description": (
            "岗位职责：负责大模型算法研发。\n"
            "任职要求：\n"
            "1. 精通 Python、PyTorch、Transformer；\n"
            "2. 熟悉大语言模型，掌握 RAG；\n"
            "3. 有 LangGraph 使用经验者优先。\n"
            "学历要求：硕士及以上，2027届优先。"
        ),
        "requirements_json": ["熟悉 Docker", "具备 MySQL 使用经验"],
        "raw_payload_json": {},
        "job_type": "internship",
        "city": "北京",
    }
    values.update(overrides)
    return Job(**values)


def test_extract_required_and_preferred_skills() -> None:
    features = extract_job_features(_job())

    assert "python" in features.required_skills
    assert "pytorch" in features.required_skills
    assert "llm" in features.required_skills or "llm" in features.mentioned_skills
    assert "langgraph" in features.preferred_skills
    # A skill in a "优先" clause must not be promoted to required.
    assert "langgraph" not in features.required_skills


def test_extract_degree_and_graduation_year() -> None:
    features = extract_job_features(_job())
    assert features.degree_requirement == "硕士"
    assert features.graduation_year_requirement == 2027
    assert features.job_type == "internship"
    assert features.city == "北京"


def test_extract_mentioned_skills_when_not_marked() -> None:
    features = extract_job_features(
        _job(
            description="岗位职责：负责后端服务开发，技术栈包括 Python 和 Docker。",
            requirements_json=[],
        )
    )
    assert "python" in features.mentioned_skills
    assert "docker" in features.mentioned_skills
    assert features.required_skills == []
    assert features.preferred_skills == []


def test_extract_empty_features_when_no_jd() -> None:
    features = extract_job_features(
        _job(description=None, requirements_json=[], raw_payload_json={})
    )
    assert features.required_skills == []
    assert features.preferred_skills == []
    assert features.degree_requirement is None
    assert features.graduation_year_requirement is None
