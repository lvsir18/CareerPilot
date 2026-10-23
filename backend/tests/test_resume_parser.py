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
    assert parsed.experiences
    kinds = {item["kind"] for item in parsed.experiences}
    assert "internship" in kinds
    assert "project" in kinds


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
