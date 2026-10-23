from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.config import Settings
from tests.conftest import AutoCsrfTestClient
from tests.factories import register_user

PDF_TEXT = "张三\n教育背景\n北京大学 计算机科学与技术 硕士\n技能\nPython PyTorch 大模型 RAG"


def _pdf_bytes(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        page.insert_text((72, y), line, fontname="china-s")
        y += 16
    content = doc.tobytes()
    doc.close()
    return content


def _docx_bytes(text: str) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def resume_app(
    settings: Settings,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> FastAPI:
    from tests.conftest import _build_app

    monkeypatch.setattr(settings, "file_storage_dir", tmp_path)
    return _build_app(settings, session_factory)


def test_upload_and_parse_pdf(resume_app: FastAPI, settings: Settings, db_session: Session) -> None:
    with AutoCsrfTestClient(resume_app, settings) as client:
        register_user(client, email="resume-a@example.com")
        response = client.post(
            "/api/v1/resumes",
            files={"file": ("resume.pdf", _pdf_bytes(PDF_TEXT), "application/pdf")},
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["parse_status"] == "success"
        assert data["parsed"]["name"] == "张三"
        assert "pytorch" in data["parsed"]["skills"]
        assert "llm" in data["parsed"]["skills"]


def test_upload_docx(resume_app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(resume_app, settings) as client:
        register_user(client, email="resume-b@example.com")
        response = client.post(
            "/api/v1/resumes",
            files={
                "file": (
                    "resume.docx",
                    _docx_bytes(PDF_TEXT),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["parse_status"] == "success"


def test_upload_rejects_wrong_format(resume_app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(resume_app, settings) as client:
        register_user(client, email="resume-c@example.com")
        response = client.post(
            "/api/v1/resumes",
            files={"file": ("resume.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "UNSUPPORTED_RESUME_FORMAT"


def test_upload_scan_like_pdf_marks_failed(resume_app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(resume_app, settings) as client:
        register_user(client, email="resume-d@example.com")
        response = client.post(
            "/api/v1/resumes",
            files={"file": ("scan.pdf", _pdf_bytes(""), "application/pdf")},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["parse_status"] == "failed"
        assert data["error"]


def test_list_get_delete_and_primary(resume_app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(resume_app, settings) as client:
        register_user(client, email="resume-e@example.com")
        first = client.post(
            "/api/v1/resumes",
            files={"file": ("a.pdf", _pdf_bytes(PDF_TEXT), "application/pdf")},
        ).json()["data"]
        second = client.post(
            "/api/v1/resumes",
            files={"file": ("b.pdf", _pdf_bytes(PDF_TEXT), "application/pdf")},
        ).json()["data"]

        assert first["is_primary"] is True
        assert second["is_primary"] is False

        listed = client.get("/api/v1/resumes").json()["data"]
        assert len(listed) == 2

        detail = client.get(f"/api/v1/resumes/{second['id']}").json()["data"]
        assert detail["filename"] == "b.pdf"

        promoted = client.post(f"/api/v1/resumes/{second['id']}/primary").json()["data"]
        assert promoted["is_primary"] is True

        assert client.delete(f"/api/v1/resumes/{first['id']}").status_code == 200
        assert client.get(f"/api/v1/resumes/{first['id']}").status_code == 404


def test_resume_cross_user_isolation(
    resume_app: FastAPI,
    settings: Settings,
) -> None:
    with AutoCsrfTestClient(resume_app, settings) as client:
        register_user(client, email="resume-owner@example.com")
        created = client.post(
            "/api/v1/resumes",
            files={"file": ("a.pdf", _pdf_bytes(PDF_TEXT), "application/pdf")},
        ).json()["data"]

        other = AutoCsrfTestClient(resume_app, settings)
        register_user(other, email="resume-other@example.com")
        assert other.get(f"/api/v1/resumes/{created['id']}").status_code == 404
        assert other.get("/api/v1/resumes").json()["data"] == []
