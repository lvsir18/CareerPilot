"""Offline browser regressions for the JD layouts reproduced on 12 career sites.

Synthetic text only: these tests never depend on live job availability.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from app.connectors.rendered_page import _EXTRACT_JS, JD_MARKERS, RenderedPageReader


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch(channel="chromium")
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


def extract(page, html: str, url: str = "https://jobs.example.com/detail/123"):
    page.route(
        "**/*", lambda route: route.fulfill(content_type="text/html; charset=utf-8", body=html)
    )
    page.goto(url)
    return page.evaluate(_EXTRACT_JS, list(JD_MARKERS))


def test_sibling_sections_preserve_responsibilities_and_qualifications(page):
    data = extract(
        page,
        f"""
        <title>校园招聘官网</title><meta property="og:title" content="校园招聘官网">
        <h1 style="display:none">招聘SEO标题</h1>
        <div class="position-title">Java开发工程师</div>
        <div class="position-meta">杭州 | 应届校招生</div>
        <main><section><div>岗位描述</div><div>{"开发服务并进行代码评审。" * 30}</div></section>
        <section><div>岗位要求</div><div>{"掌握Java与数据库。" * 15}最后一项：熟悉RAG。</div>
        </section></main>
        <footer>导航与隐私条款不属于JD</footer>
    """,
    )
    assert data["title"] == "Java开发工程师"
    assert "开发服务" in data["description"]
    assert "最后一项：熟悉RAG。" in data["description"]
    assert "导航与隐私" not in data["description"]
    assert "杭州" in data["metadata"]


def test_long_jd_is_not_silently_cut_at_four_thousand_characters(page):
    data = extract(
        page,
        f"""<h1>算法工程师</h1><main>
        <div>职位描述</div><div>{"研发基础设施与模型优化。" * 650}</div>
        <div>工作要求</div><div>{"掌握算法。" * 20}长正文末尾唯一要求</div></main>""",
    )
    assert len(data["description"]) > 6000
    assert data["description"].endswith("长正文末尾唯一要求")


def test_short_jd_at_start_of_body_is_supported(page):
    data = extract(
        page,
        f"<main><div>岗位职责</div><p>{'协作完成开发与评审。' * 6}</p>"
        f"<div>任职资格</div><p>{'熟悉Python并有项目经历。' * 4}</p></main>",
    )
    assert data["description"].startswith("岗位职责")
    assert "熟悉Python" in data["description"]


def test_job_list_is_rejected_even_if_cards_contain_full_jds(page):
    data = extract(
        page,
        f"""<title>社会招聘</title>
        <a href="/job/1">第一份职位</a><a href="/job/2">第二份职位</a>
        <main><div>职位描述</div><p>{"负责开发。" * 40}</p>
        <div>任职要求</div><p>{"熟悉Java。" * 30}</p></main>""",
        "https://jobs.example.com/jobs",
    )
    assert data["isList"] is True
    assert data["description"] is None


def test_empty_direction_labels_and_footer_do_not_become_a_successful_jd(page):
    data = extract(
        page,
        f"""<main><h1>AI Infra工程师</h1>
        <div>岗位职责</div><div>岗位要求</div><div>工作地点</div><div>部门意向</div></main>
        <footer>{"版权所有。" * 100}</footer>""",
    )
    assert data["description"] is None


def test_wait_includes_later_loaded_qualification_section(page):
    extract(
        page,
        f"""<main id="jd"><div>职位描述</div><p>{"建设数据平台。" * 30}</p></main>
        <script>setTimeout(() => {{document.querySelector('#jd').insertAdjacentHTML('beforeend',
        '<section><div>任职要求</div><p>{"掌握SQL与数据建模。" * 20}延迟加载末项</p></section>');
        }}, 1400)</script>""",
    )
    data = RenderedPageReader._wait_for_detail(page)
    assert "延迟加载末项" in data["description"]


def test_huawei_aggregate_labels_each_direction_without_reusing_previous_jd(page):
    extract(
        page,
        f"""
      <div class="position-intention"><button class="intention-select"
        onclick="document.querySelector('.aui-popover').style.display='block'">选择方向</button></div>
      <div class="aui-popover" style="display:none">
      <div class="node-label" title="算子技术" onclick="choose('算子技术')">算子技术</div>
      <div class="node-label" title="数据系统" onclick="choose('数据系统')">数据系统</div></div>
      <main><div>岗位职责</div><p id="duty"></p><div>岗位要求</div><p id="require"></p></main>
      <script>function choose(name) {{document.querySelector('.aui-popover').style.display='none';
        setTimeout(() => {{document.querySelector('#duty').innerText = name + '{"真实职责。" * 20}';
        document.querySelector('#require').innerText = name + '末项资格';}}, 700);}}</script>
    """,
        "https://career.huawei.com/cn/job-details?advertisementId=123",
    )
    data, warnings = RenderedPageReader._huawei_directions(page, {"description": None})
    assert "【岗位方向：算子技术】" in data["description"]
    assert "【岗位方向：数据系统】" in data["description"]
    assert "算子技术末项资格" in data["description"]
    assert "数据系统末项资格" in data["description"]
    assert "2 份正文" in warnings[0]


def test_location_order_and_job_type_are_taken_from_job_metadata():
    assert RenderedPageReader._guess_city("上海 / 北京 / 上海") == "上海/北京"
    assert RenderedPageReader._guess_job_type("算法工程师", "全职") == "full_time"
    assert RenderedPageReader._guess_job_type("算法工程师", "") is None
