from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.db.models.job import Job
from app.db.models.job_lead import JobLead
from app.schemas.profile import EducationItem, ExperienceItem, JobPreferences, ProfileRead
from app.services.matching_service import HeuristicV1Scorer, basic_match

JD_TEXT = """大模型算法实习生

任职要求：
精通 Python、PyTorch、Transformer、大语言模型

加分项：
LoRA、RAG、LangGraph 经验者优先
"""


def _job(**overrides) -> Job:
    values = {
        "source_id": uuid4(),
        "source_job_id": "match-test",
        "company_id": uuid4(),
        "title": "大模型算法实习生",
        "content_hash": "hash",
        "description": JD_TEXT,
        "requirements_json": [],
        "raw_payload_json": {},
        "job_type": "internship",
        "city": "北京",
    }
    values.update(overrides)
    return Job(**values)


def _profile(**overrides) -> ProfileRead:
    values = {
        "user_id": uuid4(),
        "headline": None,
        "education": [],
        "skills": ["Python", "PyTorch", "Transformer", "大语言模型", "LoRA", "RAG"],
        "experiences": [
            ExperienceItem(
                kind="internship",
                title="大模型算法实习生",
                skills=["PyTorch", "大语言模型", "RAG"],
            )
        ],
        "projects": [],
        "preferences": JobPreferences(
            job_types=["internship"],
            cities=["北京"],
            target_roles=["llm_agent"],
        ),
        "version": 1,
        "verified_by_user": True,
        "confirmed_at": None,
        "updated_at": datetime(2026, 10, 22),
    }
    values.update(overrides)
    return ProfileRead(**values)


def test_full_match_computes_skills_and_score() -> None:
    result = HeuristicV1Scorer().score(_profile(), _job())

    assert result.match_level == "full"
    assert result.match_score is not None
    assert result.match_score >= 70
    assert "python" in result.matched_skills
    assert "pytorch" in result.matched_skills
    assert "llm" in result.matched_skills
    assert "lora" in result.matched_skills
    assert "rag" in result.matched_skills
    assert "langgraph" in result.unverified_skills or any("langgraph" in g for g in result.gaps)


def test_preferred_gap_is_reported_as_unverified_not_required_failure() -> None:
    result = HeuristicV1Scorer().score(_profile(), _job())
    # LangGraph is a preferred skill the profile does not show.
    assert "langgraph" in result.unverified_skills
    # All required skills are covered, so no required-skill gap is reported.
    assert not any("必需" in gap for gap in result.gaps)


def test_eligibility_graduation_year_mismatch() -> None:
    job = _job(
        description=JD_TEXT + "\n学历要求：本科及以上\n招聘对象：2027届",
    )
    profile = _profile(
        preferences=JobPreferences(graduation_year=2026, job_types=["internship"]),
    )
    result = HeuristicV1Scorer().score(profile, job)
    assert result.eligibility_status == "ineligible"
    assert any("毕业年份" in reason for reason in result.eligibility_reasons)


def test_eligibility_degree_mismatch() -> None:
    job = _job(description=JD_TEXT + "\n学历要求：硕士及以上")
    profile = _profile(
        education=[EducationItem(school="示例大学", degree="本科")],
        preferences=JobPreferences(job_types=["internship"]),
    )
    result = HeuristicV1Scorer().score(profile, job)
    assert result.eligibility_status == "ineligible"
    assert any("学历" in reason for reason in result.eligibility_reasons)


def test_eligibility_unknown_when_requirements_missing() -> None:
    result = HeuristicV1Scorer().score(_profile(), _job(description="大模型算法实习生"))
    assert result.eligibility_status in {"unknown", "eligible"}


def test_basic_match_has_no_score() -> None:
    lead = JobLead(
        company_id=uuid4(),
        title="大模型算法实习生",
        official_url="https://example.com/job",
        source_method="search_discovery",
        dedupe_key="x",
    )
    result = basic_match(lead)
    assert result.match_level == "basic"
    assert result.match_score is None
    assert "信息不完整" in result.explanation
