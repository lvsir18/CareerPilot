"""Direct-connection catalog: the UI offers what the backend can actually do."""

from __future__ import annotations

from app.connectors.official_sources import (
    COMPANY_LABELS,
    UNSUPPORTED_NOTES,
    official_catalog,
    official_company_keys,
    supports_official,
)


def test_catalog_covers_every_company_in_the_filter() -> None:
    items = official_catalog()

    assert len(items) == len(COMPANY_LABELS) == 19
    supported = {item["key"] for item in items if item["supported"]}
    assert supported == set(official_company_keys())
    assert len(supported) == 7


def test_unsupported_companies_carry_a_reason_the_ui_can_show() -> None:
    for item in official_catalog():
        if item["supported"]:
            continue
        assert item["mode"] == "none"
        # Every greyed-out button explains itself instead of failing on click.
        assert item["note"].strip()
    assert set(UNSUPPORTED_NOTES) <= set(COMPANY_LABELS)


def test_supports_official_matches_the_registry() -> None:
    assert supports_official("tencent")
    assert supports_official("meituan")
    # JD and MiniMax were wired after the first probe round.
    assert supports_official("jd")
    assert supports_official("minimax")
    assert not supports_official("alibaba")
    assert not supports_official("huawei")


def test_unwired_companies_still_offer_an_official_search_page() -> None:
    """A grey button must lead somewhere: open the official search page."""
    for item in official_catalog():
        if item["supported"]:
            continue
        assert str(item["search_page"]).startswith("http")


def test_mixed_selection_does_not_fail_the_batch(db_session, settings, monkeypatch) -> None:
    """Picking one unwired company must not sink the whole direct search."""
    from app.services.official_jobs_service import OfficialJobsService, _Fetched

    service = OfficialJobsService(db_session, settings)
    monkeypatch.setattr(
        service,
        "_fetch",
        lambda key, keyword, limit, project=None: _Fetched(key=key, jobs=[]),
    )

    result = service.search(companies=["tencent", "alibaba"], keyword="算法", limit=3)

    summary = {row["key"]: row for row in result["companies"]}
    assert summary["tencent"]["error"] is None
    assert summary["tencent"]["mode"] == "api"
    assert summary["alibaba"]["mode"] == "none"
    assert "暂不支持官方直连" in summary["alibaba"]["error"]


def test_jd_connector_maps_the_list_payload(monkeypatch) -> None:
    from app.connectors.jd_campus import JdCampusConnector

    payload = {
        "success": True,
        "body": {
            "totalNumber": 1,
            "items": [
                {
                    "publishId": 9095,
                    "reqId": 2379,
                    "positionName": "算法工程师-数据挖掘",
                    "jobDirection": "技术方向",
                    "workContent": "负责数据挖掘与建模",
                    "qualification": "1. 本科及以上\n2. 熟悉 Python",
                    "publishTime": 1784814549000,
                }
            ],
        },
    }

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return payload

    calls: dict[str, object] = {}

    def _fake_post(url, json=None):
        calls["url"] = url
        calls["body"] = json
        return _Response()

    connector = JdCampusConnector()
    monkeypatch.setattr(connector._client, "post", _fake_post)
    try:
        rows = connector.search("算法", page_size=5)
        job = connector.to_raw_job(rows[0])
    finally:
        connector.close()

    assert calls["url"].startswith("https://campus.jd.com/api/wx/position/page")
    assert calls["body"]["parameter"]["positionName"] == "算法"
    assert job.source_job_id == "9095"
    assert job.title == "算法工程师-数据挖掘"
    assert job.description == "负责数据挖掘与建模"
    assert job.requirements == ["1. 本科及以上", "2. 熟悉 Python"]
    assert job.job_type == "campus"
    assert job.published_at is not None
