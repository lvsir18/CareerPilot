"""Any-company link preview: SSRF guard + draft mapping."""

from __future__ import annotations

import pytest

from app.connectors.errors import ConnectorParseError, UnsafeUrlError
from app.connectors.rendered_page import PageSnapshot, RenderedPageReader, assert_public_url
from app.core.errors import AppError


def test_public_url_guard_rejects_local_and_private_targets() -> None:
    for bad in (
        "file:///etc/passwd",
        "http://127.0.0.1/job",
        "http://localhost:3000/job",
        "http://10.0.0.5/job",
        "http://169.254.169.254/latest/meta-data",
        "https://user:pass@jobs.example.com/x",
    ):
        with pytest.raises(UnsafeUrlError):
            assert_public_url(bad)


def test_public_url_guard_accepts_a_public_page() -> None:
    assert assert_public_url("https://campus.dewu.com/578078/position/list")


def test_preview_returns_a_draft_for_any_company(settings, monkeypatch) -> None:
    from app.services.link_preview_service import LinkPreviewService

    monkeypatch.setattr(RenderedPageReader, "available", lambda self: (True, "可用"))
    monkeypatch.setattr(
        RenderedPageReader,
        "read",
        lambda self, url: PageSnapshot(
            url=url,
            final_url="https://campus.dewu.com/578078/position/123",
            title="推荐算法实习生",
            description="岗位职责：负责推荐模型。\n任职要求：熟悉 Python。",
            city="上海",
            warnings=[],
        ),
    )

    preview = LinkPreviewService(settings).preview("https://campus.dewu.com/x")

    assert preview["title"] == "推荐算法实习生"
    assert preview["company"] == "得物"
    assert preview["city"] == "上海"
    assert "推荐模型" in preview["description"]
    assert preview["source"] == "rendered"


def test_preview_maps_reader_failure_to_a_correctable_error(settings, monkeypatch) -> None:
    from app.services.link_preview_service import LinkPreviewService

    monkeypatch.setattr(RenderedPageReader, "available", lambda self: (True, "可用"))

    def _boom(self, url):
        raise ConnectorParseError("没能从这个页面读到 JD 正文")

    monkeypatch.setattr(RenderedPageReader, "read", _boom)

    with pytest.raises(AppError) as exc:
        LinkPreviewService(settings).preview("https://career.huawei.com/x")

    assert exc.value.code == "LINK_PREVIEW_FAILED"
    assert "粘贴" in exc.value.message
