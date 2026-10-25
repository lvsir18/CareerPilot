from __future__ import annotations

import io

import pytest

from app.services.resume_parser import (
    EmptyResumeText,
    UnsupportedResumeFormat,
    extract_text,
    parse_resume_text,
)
from app.services.skill_normalizer import extract_skills, normalize_skill

RESUME_TEXT = """张三
电话：13812345678
邮箱：zhangsan@example.com

教育背景
北京大学 计算机科学与技术 硕士 2024年入学 2027年毕业

专业技能
Python、PyTorch、Transformer、大语言模型、RAG、LangChain、Docker、MySQL

实习经历
2026年6月 - 2026年9月 某科技公司 大模型算法实习生
参与RAG系统开发，使用PyTorch和LangChain

项目经历
基于Transformer的文本分类
"""


def test_extract_text_from_pdf() -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Python 大模型 实习")
    content = doc.tobytes()
    doc.close()

    text = extract_text(content, "resume.pdf")
    assert "Python" in text


def test_extract_text_from_docx() -> None:
    import docx

    document = docx.Document()
    document.add_paragraph("Python 大模型 实习")
    buffer = io.BytesIO()
    document.save(buffer)

    text = extract_text(buffer.getvalue(), "resume.docx")
    assert "Python" in text


def test_extract_text_rejects_unsupported_format() -> None:
    with pytest.raises(UnsupportedResumeFormat):
        extract_text(b"x", "resume.txt")


def test_extract_text_empty_pdf_is_scan_like() -> None:
    import fitz

    doc = fitz.open()
    doc.new_page()  # blank page with no text
    content = doc.tobytes()
    doc.close()

    with pytest.raises(EmptyResumeText):
        extract_text(content, "resume.pdf")


def test_parse_resume_extracts_fields_and_masks_contact() -> None:
    parsed = parse_resume_text(RESUME_TEXT)

    assert parsed.name == "张三"
    assert parsed.phone == "138****5678"
    assert parsed.email == "zh******@example.com"
    assert parsed.education
    assert parsed.education[0]["school"] == "北京大学"
    assert parsed.education[0]["degree"] == "硕士"
    assert parsed.education[0]["graduation_year"] == 2027
    assert parsed.education[0]["start_year"] == 2024


def test_parse_resume_extracts_skills_and_experiences() -> None:
    parsed = parse_resume_text(RESUME_TEXT)

    assert "python" in parsed.skills
    assert "pytorch" in parsed.skills
    assert "transformer" in parsed.skills
    assert "llm" in parsed.skills
    assert "rag" in parsed.skills
    assert "langchain" in parsed.skills
    # Internships and projects are separate panels now.
    assert parsed.experiences
    assert {item["kind"] for item in parsed.experiences} == {"internship"}
    assert parsed.projects
    assert {item["kind"] for item in parsed.projects} <= {"project", "research"}


def test_parse_resume_short_text_is_scan_like() -> None:
    parsed = parse_resume_text("张三\n")
    assert parsed.is_scan_like is True
    assert parsed.warnings


def test_parse_resume_does_not_invent_fields() -> None:
    parsed = parse_resume_text("只有一句没有任何结构化信息的话")
    assert parsed.skills == []
    assert parsed.education == []
    assert parsed.experiences == []
    assert parsed.name is None


def test_skill_normalizer_canonicalizes_and_distinguishes_hypernyms() -> None:
    assert normalize_skill("PyTorch") == "pytorch"
    assert normalize_skill("大模型") == "llm"
    assert normalize_skill("RAG") == "rag"
    assert normalize_skill("LangGraph") == "langgraph"
    assert normalize_skill("LangChain") == "langchain"
    # PyTorch must not imply DeepSpeed.
    assert normalize_skill("PyTorch") != "deepspeed"

    skills = extract_skills("熟悉 PyTorch、大语言模型、LangGraph")
    assert "pytorch" in skills
    assert "llm" in skills
    assert "langgraph" in skills


def test_internships_and_projects_are_separated_by_section() -> None:
    """A real resume layout: sections, then title line + date line + bullets."""
    text = """张三
教育背景
某大学 计算机 本科 2021-2025
实习经历
某某科技有限公司｜算法实习生
2025.10 - 2026.01
• 负责推荐模型训练与评估。
项目经历
实验室横向项目- 基于自然语言理解的语音交互软件
2026.4 - 至今
• 构建知识库与意图识别链路。
GoldAgent - LLM 增强的分析系统
2026.05 - 至今
• 实现行情获取到报告生成的链路。
科研经历
多航空器轨迹预测研究
2026 - 至今
• 构建时空交互预测模型。
专业技能
Python / PyTorch
"""

    parsed = parse_resume_text(text)

    assert [(item["title"], item["time_range"]) for item in parsed.experiences] == [
        ("某某科技有限公司｜算法实习生", "2025.10 - 2026.01")
    ]
    titles = [item["title"] for item in parsed.projects]
    # The project title above the date line must not be swallowed by the
    # previous entry, and "语言" inside a title must not delete the line.
    assert titles == [
        "实验室横向项目- 基于自然语言理解的语音交互软件",
        "GoldAgent - LLM 增强的分析系统",
        "多航空器轨迹预测研究",
    ]
    assert parsed.projects[0]["time_range"] == "2026.04 - 至今"
    # Skills belong to no panel and must not leak into the last project.
    assert all("PyTorch" not in (item["description"] or "") for item in parsed.projects)


def test_awards_are_kept_out_of_both_panels() -> None:
    text = """张三
实习经历
某公司｜实习生
2025.01 - 2025.06
• 做了一些事。
获奖情况
国家励志奖学金
综合荣誉
优秀学生
"""

    parsed = parse_resume_text(text)

    assert [item["kind"] for item in parsed.experiences] == ["internship"]
    assert parsed.awards
    assert all("奖学金" not in (item["title"] or "") for item in parsed.experiences)
    assert all("奖学金" not in (item["title"] or "") for item in parsed.projects)
