from __future__ import annotations

from app.search.taxonomy import (
    classify_job_families,
    classify_job_family,
    job_family_matches,
)


def test_one_posting_can_belong_to_several_families() -> None:
    """「大模型算法工程师」既是算法也是大模型，筛哪个都该出现。"""
    labels = classify_job_families("大模型算法工程师")

    assert "algorithm" in labels
    assert "llm" in labels


def test_a_passing_mention_in_the_jd_does_not_reclassify_the_role() -> None:
    """JD 里顺带提一句大模型，不能把后端岗判成大模型岗。"""
    labels = classify_job_families(
        "Java 后端开发工程师",
        "负责大模型 / Agent 相关服务的接口开发与性能优化",
    )

    assert labels == ["backend"]
    assert classify_job_family("Java 后端开发工程师", "涉及大模型") == "backend"


def test_the_jd_is_only_a_fallback_when_the_title_is_silent() -> None:
    labels = classify_job_families("", "负责大模型推理优化与部署")

    assert labels == ["llm"]


def test_filter_matches_any_label_and_umbrella_groups() -> None:
    labels = classify_job_families("AI Agent算法工程师（大模型方向）")

    assert job_family_matches(labels, "algorithm")
    assert job_family_matches(labels, "agent")
    assert job_family_matches(labels, "llm")
    # Umbrella filter: 一次看到大模型 / Agent / 算法。
    assert job_family_matches(labels, "ai")
    assert not job_family_matches(labels, "frontend")
    assert job_family_matches(labels, None)


def test_unknown_text_falls_back_to_other() -> None:
    assert classify_job_families("", "") == ["other"]
    assert classify_job_families("神秘岗位XYZ") == ["other"]


def test_big_family_groups_cover_every_member() -> None:
    """前端只暴露 8 个大类，组内任何细分标签都要能匹配上。"""
    from app.search.taxonomy import is_known_family

    assert is_known_family("ai")
    assert is_known_family("engineering")
    assert is_known_family("product_design")

    assert job_family_matches(["backend"], "engineering")
    assert job_family_matches(["frontend"], "engineering")
    assert job_family_matches(["client"], "engineering")
    assert job_family_matches(["infra"], "engineering")
    assert job_family_matches(["design"], "product_design")
    assert not job_family_matches(["data"], "engineering")
    assert not job_family_matches(["product"], "ai")
