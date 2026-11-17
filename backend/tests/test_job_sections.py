from app.services.job_sections import split_job_sections


def test_alibaba_separates_duties_five_requirements_and_business():
    text = (
        "职位描述\n1. 设计评测。\n2. 分析反馈。\n职位要求\n"
        + "\n".join(f"{i}. 资格{i}。" for i in range(1, 6))
        + "\n在招业务\nToken Foundry"
    )
    result = split_job_sections(text)
    assert result.description == "职位描述\n1. 设计评测。\n2. 分析反馈。"
    assert result.requirements == [f"{i}. 资格{i}。" for i in range(1, 6)]
    assert result.additional_info == "在招业务\nToken Foundry"


def test_qualification_heading_in_an_ordinary_sentence_does_not_split_the_sentence():
    text = "职位描述\n负责制定岗位要求并设计数据验收方案。"
    result = split_job_sections(text)
    assert result.description == text
    assert result.requirements == []


def test_benefits_and_locations_do_not_leak_into_qualifications():
    result = split_job_sections(
        "岗位描述\n开发。\n岗位要求\n熟悉Java。\n加入我们的理由：\n导师带教。\n工作地点\n杭州"
    )
    assert result.requirements == ["熟悉Java。"]
    assert result.additional_info == "加入我们的理由：\n导师带教。\n工作地点\n杭州"


def test_huawei_directions_stay_associated_with_each_requirement():
    result = split_job_sections(
        "【岗位方向：算子技术】\n岗位职责\n研发算子。\n岗位要求\n熟悉C++。\n工作地点\n深圳\n"
        "【岗位方向：数据系统】\n岗位职责\n建设数据平台。\n岗位要求\n熟悉SQL。"
    )
    assert result.requirements == [
        "【岗位方向：算子技术】",
        "熟悉C++。",
        "【岗位方向：数据系统】",
        "熟悉SQL。",
    ]
    assert "研发算子" in result.description and "建设数据平台" in result.description
    assert "熟悉SQL" not in result.description
    assert "【岗位方向：算子技术】" in result.additional_info


def test_deepseek_direction_labels_and_bonus_requirements_are_preserved():
    result = split_job_sections(
        "大模型研究平台方向\n岗位职责\n研发平台。\n岗位要求\n熟悉Python。\n加分项\n开源贡献。\n"
        "Agent 框架组件方向\n岗位职责\n研发SDK。\n岗位要求\n熟悉MCP。"
    )
    assert result.requirements == [
        "大模型研究平台方向",
        "熟悉Python。",
        "加分项",
        "开源贡献。",
        "Agent 框架组件方向",
        "熟悉MCP。",
    ]
    assert "开源贡献" not in result.description


def test_unstructured_text_is_preserved_without_guessing_a_boundary():
    result = split_job_sections("负责研发平台，欢迎熟悉算法的同学。")
    assert result.description == "负责研发平台，欢迎熟悉算法的同学。"
    assert result.requirements == []
