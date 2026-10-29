from __future__ import annotations

import pytest

from app.connectors.errors import ConnectorParseError
from app.connectors.tencent_campus import TencentCampusConnector, classify_job_type
from app.core.config import Settings


class FakeClient:
    """Stands in for SafeHttpClient so tests never touch the network."""

    def __init__(self, search=None, detail=None) -> None:
        self.search = search or {"status": 0, "data": {"positionList": []}}
        self.detail = detail or {"status": 0, "data": {}}
        self.calls: list[tuple[str, str]] = []

    def post_json(self, url: str, payload: dict) -> dict:
        self.calls.append(("POST", url))
        return self.search

    def get_json(self, url: str) -> dict:
        self.calls.append(("GET", url))
        return self.detail

    def close(self) -> None:
        return None


def _connector(client: FakeClient) -> TencentCampusConnector:
    return TencentCampusConnector(Settings(), client=client)


def _position(project: str, post_id: str = "1") -> dict:
    return {
        "positionTitle": "算法-机器学习方向",
        "projectName": project,
        "postId": post_id,
        "workCities": "深圳总部",
    }


def _detail(**overrides) -> dict:
    payload = {
        "postId": "1212183855952704516",
        "title": "算法-机器学习方向",
        "desc": "负责推荐系统模型优化。",
        "request": "1. 熟悉机器学习；\n2. 熟悉 PyTorch。",
        "workCityList": ["深圳总部"],
        "projectId": 4,
        "projectName": "日常实习",
        "tidName": "技术",
        "intentionBGDList": [{"showTitle": "TEG"}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("project", "expected"),
    [
        ("日常实习", "internship"),
        ("应届实习", "internship"),
        ("青云计划-实习生", "internship"),
        ("应届毕业生", "campus"),
        ("青云计划-应届生", "campus"),
        (None, None),
    ],
)
def test_classify_job_type(project, expected):
    assert classify_job_type(project) == expected


def test_search_keeps_only_requested_project():
    client = FakeClient(
        search={
            "status": 0,
            "data": {
                "positionList": [
                    _position("应届毕业生", "1"),
                    _position("日常实习", "2"),
                    _position("青云计划-实习生", "3"),
                ]
            },
        }
    )
    rows = _connector(client).search("算法", project="日常实习")
    assert [row["postId"] for row in rows] == ["2"]


def test_to_raw_job_maps_source_fields():
    raw = _connector(FakeClient()).to_raw_job(_detail())

    assert raw.company == "腾讯"
    assert raw.title == "算法-机器学习方向"
    assert raw.job_type == "internship"
    assert raw.recruitment_program == "日常实习"
    assert raw.city == "深圳"
    assert raw.department == "TEG"
    assert raw.source_url == ("https://join.qq.com/post_detail.html?postid=1212183855952704516")
    assert raw.verification_status.value == "verified"
    assert raw.published_at is None
    assert raw.requirements == ["1. 熟悉机器学习；", "2. 熟悉 PyTorch。"]


def test_detail_rejects_delisted_posting():
    client = FakeClient(detail={"status": 404, "message": "岗位已下架", "data": None})
    with pytest.raises(ConnectorParseError):
        _connector(client).detail("missing")


def test_search_rejects_error_payload():
    client = FakeClient(search={"status": 500, "message": "system busy", "data": None})
    with pytest.raises(ConnectorParseError):
        _connector(client).search("算法")


def test_search_treats_null_position_list_as_no_match():
    """A zero-result query answers ``positionList: null``, not ``[]``.

    Treating that as a broken schema used to abort the whole agent step with an
    opaque ``import_official_jobs: TOOL_FAILED``.
    """
    client = FakeClient(search={"status": 0, "data": {"positionList": None, "count": 0}})

    assert _connector(client).search("成都") == []


def test_search_rejects_malformed_position_list():
    client = FakeClient(search={"status": 0, "data": {"positionList": "oops"}})
    with pytest.raises(ConnectorParseError):
        _connector(client).search("算法")


def test_import_jobs_turns_connector_errors_into_business_errors(monkeypatch):
    from app.core.errors import AppError
    from app.services import tencent_campus_service as module

    class BrokenConnector:
        def __init__(self, settings) -> None:
            pass

        def search(self, *args, **kwargs):
            raise ConnectorParseError("腾讯校招接口返回异常：system busy")

        def close(self) -> None:
            return None

    monkeypatch.setattr(module, "TencentCampusConnector", BrokenConnector)
    service = module.TencentCampusService(session=None, settings=Settings())

    with pytest.raises(AppError) as excinfo:
        service.import_jobs(keyword="成都", project="日常实习")

    # A connector error must not reach the agent tool wrapper as TOOL_FAILED.
    assert excinfo.value.code == "TENCENT_CAMPUS_UNAVAILABLE"
    assert "腾讯校招接口返回异常" in excinfo.value.message
