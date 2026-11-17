from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.enums import JobStatus
from tests.factories import create_job, register_user


def test_jobs_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/jobs").status_code == 401


def test_job_list_pagination_and_shape(client: TestClient, db_session: Session) -> None:
    register_user(client)
    for index in range(25):
        create_job(
            db_session,
            title=f"Agent 实习生 {index:02d}",
            company="Paginate 公司",
            source_job_id=f"page-{index:02d}",
            published_at=datetime(2026, 10, 1, tzinfo=UTC),
        )

    response = client.get("/api/v1/jobs", params={"page": 2, "page_size": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"page": 2, "page_size": 10, "total": 25}
    assert len(body["data"]) == 10
    first = body["data"][0]
    assert first["company"] == "Paginate 公司"
    assert first["source_type"] == "manual"
    assert first["source_url"].startswith("https://")
    assert first["is_demo"] is False


def test_job_filters_and_sort(client: TestClient, db_session: Session) -> None:
    register_user(client)
    create_job(
        db_session,
        source_job_id="filter-1",
        company="北京智研",
        city="北京",
        title="LLM 算法实习",
        description="负责大模型推理优化与评测。",
        job_type="internship",
        source_type="manual",
        published_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    create_job(
        db_session,
        source_job_id="filter-2",
        company="上海云图",
        city="上海",
        title="后端校招",
        description="负责服务端接口与存储。",
        job_type="campus",
        source_type="fixture",
        published_at=datetime(2026, 10, 5, tzinfo=UTC),
        status=JobStatus.CLOSED,
    )
    create_job(
        db_session,
        source_job_id="filter-3",
        company="未知日期公司",
        city="深圳",
        location_text="深圳·南山",
        title="Agent 平台实习",
        description="负责 Agent 工具链与评测。",
        job_type="internship",
        published_at=None,
    )

    by_city = client.get("/api/v1/jobs", params={"cities": "北京,上海"}).json()
    assert [item["city"] for item in by_city["data"]] == ["上海", "北京"]

    by_company = client.get("/api/v1/jobs", params={"companies": "上海云图"}).json()
    assert by_company["meta"]["total"] == 1

    by_type = client.get("/api/v1/jobs", params={"job_types": "internship"}).json()
    assert by_type["meta"]["total"] == 2

    by_source = client.get("/api/v1/jobs", params={"source_types": "fixture"}).json()
    assert by_source["meta"]["total"] == 1

    by_status = client.get("/api/v1/jobs", params={"status": "closed"}).json()
    assert by_status["meta"]["total"] == 1

    known_dates = client.get("/api/v1/jobs", params={"published_date_known": "true"}).json()
    assert known_dates["meta"]["total"] == 2
    unknown_dates = client.get("/api/v1/jobs", params={"published_date_known": "false"}).json()
    assert unknown_dates["meta"]["total"] == 1
    assert unknown_dates["data"][0]["published_at"] is None

    keyword = client.get("/api/v1/jobs", params={"q": "agent"}).json()
    assert keyword["meta"]["total"] == 1
    assert keyword["data"][0]["title"] == "Agent 平台实习"

    # Default sort places known publish dates first; NULL is never "recent".
    ordered = client.get("/api/v1/jobs").json()["data"]
    assert ordered[-1]["published_at"] is None


def test_job_program_demo_and_keyword_filters(client: TestClient, db_session: Session) -> None:
    register_user(client)
    create_job(
        db_session,
        source_job_id="program-1",
        title="大模型实习",
        description="负责大模型训练。",
        recruitment_program="2027届秋招",
        is_demo=False,
    )
    create_job(
        db_session,
        source_job_id="program-2",
        title="Agent 实习",
        description="负责 Agent 平台。",
        recruitment_program="日常实习",
        is_demo=True,
    )

    by_program = client.get("/api/v1/jobs", params={"recruitment_program": "2027届秋招"}).json()
    assert by_program["meta"]["total"] == 1
    assert by_program["data"][0]["recruitment_program"] == "2027届秋招"

    demo_only = client.get("/api/v1/jobs", params={"is_demo": "true"}).json()
    assert demo_only["meta"]["total"] == 1
    assert demo_only["data"][0]["is_demo"] is True

    keyword_alias = client.get("/api/v1/jobs", params={"keyword": "Agent"}).json()
    assert keyword_alias["meta"]["total"] == 1


def test_job_date_range_validation(client: TestClient) -> None:
    register_user(client)

    response = client.get(
        "/api/v1/jobs",
        params={
            "published_after": "2026-10-20T00:00:00Z",
            "published_before": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DATE_RANGE"

    too_large = client.get("/api/v1/jobs", params={"page_size": 51})
    assert too_large.status_code == 422


def test_job_detail_and_unknown_id(client: TestClient, db_session: Session) -> None:
    register_user(client)
    job = create_job(db_session, source_job_id="detail-1", description="完整 JD 文本")

    response = client.get(f"/api/v1/jobs/{job.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"] == job.title
    assert data["description"] == "完整 JD 文本"
    assert data["source_url"] == job.source_url
    assert data["published_at"] is not None

    missing = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_demo_jobs_are_hidden_outside_demo_mode(
    non_demo_client: TestClient, db_session: Session
) -> None:
    register_user(non_demo_client)
    demo_job = create_job(db_session, source_job_id="demo-hidden", is_demo=True)

    listing = non_demo_client.get("/api/v1/jobs").json()
    assert listing["meta"]["total"] == 0

    detail = non_demo_client.get(f"/api/v1/jobs/{demo_job.id}")
    assert detail.status_code == 404

    save = non_demo_client.post(f"/api/v1/jobs/{demo_job.id}/save", json={})
    assert save.status_code == 404

    application = non_demo_client.post("/api/v1/applications", json={"job_id": str(demo_job.id)})
    assert application.status_code == 404


def test_demo_jobs_are_labelled_in_demo_mode(client: TestClient, db_session: Session) -> None:
    register_user(client)
    create_job(db_session, source_job_id="demo-visible", is_demo=True)

    listing = client.get("/api/v1/jobs").json()

    assert listing["meta"]["total"] == 1
    assert listing["data"][0]["is_demo"] is True
