"""Parser tests for the browser-rendered official sources.

No browser is launched here: fixtures are the JSON shapes the sites actually
return, so the heuristics stay regression-tested without network access.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.connectors.official_sources import RENDERED_SOURCES
from app.connectors.rendered import RenderedJobSearch, find_job_list, split_jd
from app.core.config import Settings

BYTEDANCE_PAYLOAD = {
    "code": 0,
    "data": {
        "count": 2,
        "city_list": [{"code": "CT_11", "name": "北京"}, {"code": "CT_12", "name": "上海"}],
        "job_post_list": [
            {
                "id": "7561877805658196229",
                "title": "算法实习生-抖音研发",
                "description": "1、负责推荐系统排序模型优化；",
                "requirement": "1、熟悉机器学习；",
                "city_info": {"code": "CT_11", "name": "北京"},
                "recruit_type": {"name": "实习", "parent": {"name": "校招"}},
                "publish_time": 1760637885855,
            },
            {
                "id": "7650055149298207029",
                "title": "大模型算法实习生-Data AML",
                "description": "参与大模型训练；",
                "requirement": "熟悉 PyTorch；",
                "city_info": {"code": "CT_12", "name": "上海"},
                "recruit_type": {"name": "实习", "parent": {"name": "校招"}},
            },
        ],
    },
}


def _search() -> RenderedJobSearch:
    return RenderedJobSearch(Settings())


def test_find_job_list_ignores_city_enums():
    rows = find_job_list(BYTEDANCE_PAYLOAD)
    assert rows is not None
    assert len(rows) == 2
    assert rows[0]["title"] == "算法实习生-抖音研发"


def test_find_job_list_returns_none_without_job_columns():
    payload = {"data": {"city_list": [{"code": "CT_11", "name": "北京"}]}}
    assert find_job_list(payload) is None


def test_to_raw_job_maps_official_fields():
    spec = RENDERED_SOURCES["bytedance"]
    row = BYTEDANCE_PAYLOAD["data"]["job_post_list"][0]
    raw = _search()._to_raw_job(spec, row, datetime.now(UTC))

    assert raw is not None
    assert raw.company == "字节跳动"
    assert raw.title == "算法实习生-抖音研发"
    assert raw.city == "北京"
    # "校招/实习" must resolve to internship, not campus.
    assert raw.job_type == "internship"
    assert raw.source_url == (
        "https://jobs.bytedance.com/campus/position/7561877805658196229/detail"
    )
    assert raw.description and "推荐系统" in raw.description
    assert raw.requirements == ["1、熟悉机器学习；"]
    assert raw.published_at is not None
    assert raw.published_at.year == 2025  # epoch millis 1760637885855 → 2025-10-16


def test_to_raw_job_skips_rows_without_title():
    spec = RENDERED_SOURCES["bytedance"]
    raw = _search()._to_raw_job(spec, {"id": "1", "description": "x"}, datetime.now(UTC))
    assert raw is None


# Real shapes returned by the other campus sites (trimmed to the used columns).
BILIBILI_ROW = {
    "id": 30904,
    "positionName": "Agent开发工程师【2027届】",
    "positionDescription": "工作职责:\n1、建设 Agent 运行时。\n工作要求:\n1、2027届本科及以上。",
    "positionTypeName": "全职",
    "postCodeName": "技术类",
    "workLocation": "上海市",
    "pushTime": "2026-10-15 22:08:19",
}

XIAOHONGSHU_ROW = {
    "positionId": 22013,
    "positionName": "【2027校招】媒体网络研发工程师-流媒体方向",
    "workplace": "北京市，上海市",
    "duty": "1、参与研发媒体网络核心模块；",
    "qualification": "1、本科及以上学历；",
    "publishTime": "2026-10-23",
    "jobType": "campus",
}

MEITUAN_ROW = {
    "jobUnionId": "4697320043",
    "name": "AI全栈工程师",
    "jobDuty": "负责算法工程落地；",
    "jobRequirement": "熟悉 Python；",
    "cityList": [{"name": "北京市"}, {"name": "上海市"}],
    "firstPostTime": "2026-09-01 10:00:00",
}


def test_bilibili_combined_jd_is_split():
    raw = _search()._to_raw_job(RENDERED_SOURCES["bilibili"], BILIBILI_ROW, datetime.now(UTC))
    assert raw is not None
    assert raw.title == "Agent开发工程师【2027届】"
    assert raw.city == "上海"
    assert raw.job_type == "campus"
    assert raw.description and "Agent 运行时" in raw.description
    assert "2027届" not in (raw.description or "")
    assert raw.requirements and "2027届本科及以上" in raw.requirements[0]
    assert raw.source_url == "https://jobs.bilibili.com/campus/positions/30904"
    # Date strings must not be mistaken for epoch values.
    assert raw.published_at is not None
    assert raw.published_at.year == 2026


def test_xiaohongshu_multi_city_and_date_string():
    raw = _search()._to_raw_job(RENDERED_SOURCES["xiaohongshu"], XIAOHONGSHU_ROW, datetime.now(UTC))
    assert raw is not None
    assert raw.city == "北京"
    assert raw.location_text == "北京市，上海市"
    assert raw.description and "媒体网络" in raw.description
    assert raw.requirements == ["1、本科及以上学历；"]
    assert raw.source_url == "https://job.xiaohongshu.com/campus/position/22013"
    assert raw.published_at is not None
    assert raw.published_at.month == 10


def test_meituan_city_list_and_detail_url():
    raw = _search()._to_raw_job(RENDERED_SOURCES["meituan"], MEITUAN_ROW, datetime.now(UTC))
    assert raw is not None
    assert raw.title == "AI全栈工程师"
    assert raw.city == "北京"
    assert raw.job_type == "campus"
    assert raw.source_url == (
        "https://zhaopin.meituan.com/web/position/detail?jobUnionId=4697320043&jobShareType=1"
    )
    assert raw.requirements == ["熟悉 Python；"]


def test_split_jd_without_marker_keeps_description():
    desc, req = split_jd("只写了职责，没有要求段。")
    assert desc == "只写了职责，没有要求段。"
    assert req is None
