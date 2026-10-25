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
            description="岗位职责\n负责推荐模型。\n任职要求\n熟悉 Python。\n在招业务\n推荐团队",
            city="上海",
            warnings=[],
        ),
    )

    preview = LinkPreviewService(settings).preview("https://campus.dewu.com/x")

    assert preview["title"] == "推荐算法实习生"
    assert preview["company"] == "得物"
    assert preview["city"] == "上海"
    assert "推荐模型" in preview["description"]
    assert "熟悉 Python" not in preview["description"]
    assert preview["requirements"] == ["熟悉 Python。"]
    assert preview["additional_info"] == "在招业务\n推荐团队"
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


@pytest.mark.parametrize(
    ("url", "company"),
    [
        ("https://360campus.zhiye.com/intern/detail?jobAdId=1", "360"),
        ("https://xiaomi.jobs.f.mioffice.cn/internship/position/1/detail", "小米"),
        ("https://app.mokahr.com/apply/moonshot/148506#/job/1", "月之暗面 Kimi"),
        ("https://app.mokahr.com/social-recruitment/high-flyer/140576#/job/1", "DeepSeek"),
        ("https://app.mokahr.com/campus-recruitment/trip/117988#/job/1", "携程"),
        ("https://app.mokahr.com/apply/moonshot/1485069#/job/1", None),
        ("https://app.mokahr.com/apply/another-company/148506#/job/1", None),
    ],
)
def test_company_labels_only_match_exact_known_ats_tenants(url, company):
    from app.services.link_preview_service import _company_from_url

    assert _company_from_url(url) == company
