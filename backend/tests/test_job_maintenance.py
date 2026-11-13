from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.connectors.rendered_page import detect_posting_status
from app.core.config import Settings
from app.db.models.enums import JobStatus
from app.db.models.job import Job
from app.db.models.job_maintenance import JobMaintenanceRun
from app.db.models.saved_job import SavedJob
from app.db.models.user import User
from app.services.job_maintenance_service import JobMaintenanceService
from tests.conftest import AutoCsrfTestClient
from tests.factories import create_job, register_user


# --------------------------------------------------------------------- status
def test_explicit_closure_statement_closes_a_posting() -> None:
    status, evidence = detect_posting_status(
        title="Agent 算法实习生",
        description="职位已下架，感谢关注我们的招聘。" * 4,
        target_url="https://jobs.example.com/position/1",
        final_url="https://jobs.example.com/position/1",
    )

    assert status is JobStatus.CLOSED
    assert "职位已下架" in (evidence or "")


def test_login_wall_is_unconfirmed_not_closed() -> None:
    status, evidence = detect_posting_status(
        title="登录",
        description="请登录后查看岗位详情" * 10,
        target_url="https://jobs.example.com/position/1",
        final_url="https://jobs.example.com/login",
    )

    assert status is JobStatus.UNKNOWN
    assert "登录" in (evidence or "")


def test_redirect_to_list_page_is_unconfirmed() -> None:
    status, _evidence = detect_posting_status(
        title="岗位列表",
        description="这里有很多岗位" * 20,
        target_url="https://jobs.example.com/position/123",
        final_url="https://jobs.example.com/position",
    )

    assert status is JobStatus.UNKNOWN


def test_empty_body_is_unconfirmed() -> None:
    status, _evidence = detect_posting_status(
        title=None,
        description="",
        target_url="https://jobs.example.com/position/1",
        final_url="https://jobs.example.com/position/1",
    )

    assert status is JobStatus.UNKNOWN


def test_normal_detail_is_open() -> None:
    status, evidence = detect_posting_status(
        title="Agent 算法实习生",
        description="岗位职责：负责 Agent 评测。" * 10,
        target_url="https://jobs.example.com/position/1",
        final_url="https://jobs.example.com/position/1",
    )

    assert status is JobStatus.OPEN
    assert evidence


# -------------------------------------------------------------------- service
def _user(session: Session, email: str = "maintainer@example.com") -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _service(session: Session, settings: Settings) -> JobMaintenanceService:
    return JobMaintenanceService(session, settings)


def test_repeat_request_reuses_the_active_run(db_session, settings: Settings) -> None:
    user = _user(db_session)
    service = _service(db_session, settings)

    first, created_first = service.create_run(
        user, kind="refresh", scope={"q": "大模型"}, options={"recheck": True}
    )
    second, created_second = service.create_run(
        user, kind="refresh", scope={"q": "大模型"}, options={"recheck": True}
    )

    assert created_first is True
    assert created_second is False
    assert first.id == second.id


def test_claim_is_single_winner(db_session, settings: Settings) -> None:
    user = _user(db_session, "claim@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(user, kind="refresh", scope={}, options={})

    assert service.claim(run.id) is not None
    assert service.claim(run.id) is None


def test_recheck_with_same_content_keeps_the_job_and_marks_checked(
    db_session, settings: Settings, monkeypatch
) -> None:
    job = create_job(
        db_session,
        title="大模型算法实习生",
        company="字节跳动",
        city="北京",
        job_type="internship",
        description="负责大模型训练。" * 12,
    )
    # The factory stores a placeholder hash; align it so this test observes the
    # "checked, nothing changed" branch instead of a content update.
    from app.connectors.schemas import RawJob
    from app.services.job_ingestion import compute_content_hash

    job.content_hash = compute_content_hash(
        RawJob(
            source_type=job.source.source_type,
            source_key=job.source.source_key,
            source_job_id=job.source_job_id,
            company=job.company.name,
            title=job.title,
            source_url=job.source_url,
            description=job.description,
            department=job.department,
            recruitment_program=job.recruitment_program,
            location_text=job.location_text,
            city=job.city,
            job_type=job.job_type,
            requirements=job.requirements_json,
        )
    )
    db_session.commit()
    job_id = job.id
    first_seen = job.first_seen_at
    before = db_session.query(Job).count()

    def fake_read(self, target: Job) -> dict:
        return {
            "status": JobStatus.OPEN,
            "title": target.title,
            "description": target.description,  # identical content
            "city": target.city,
            "location_text": target.location_text,
            "job_type": target.job_type,
            "evidence": "读到官方详情正文",
        }

    monkeypatch.setattr(JobMaintenanceService, "_read_page", fake_read)

    user = _user(db_session, "recheck@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(user, kind="refresh", scope={}, options={})
    service.execute_refresh(run.id, recheck=True, discover=False)

    db_session.refresh(job)
    assert job.id == job_id
    assert job.first_seen_at == first_seen
    assert job.last_checked_at is not None
    assert db_session.query(Job).count() == before
    result = db_session.get(JobMaintenanceRun, run.id)
    assert result is not None
    assert result.status == "success"
    assert result.result_json["counters"]["unchanged"] >= 1


def test_recheck_failure_keeps_the_original_status(
    db_session, settings: Settings, monkeypatch
) -> None:
    job = create_job(db_session, title="后端实习生", company="美团")
    job.status = JobStatus.OPEN
    db_session.commit()

    def boom(self, target: Job) -> dict:
        raise TimeoutError("页面打开超时")

    monkeypatch.setattr(JobMaintenanceService, "_read_page", boom)

    user = _user(db_session, "unconfirmed@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(user, kind="refresh", scope={}, options={})
    service.execute_refresh(run.id, recheck=True, discover=False)

    db_session.refresh(job)
    assert job.status is JobStatus.OPEN  # unchanged: never guess "closed"
    result = db_session.get(JobMaintenanceRun, run.id)
    assert result is not None
    assert result.status == "partial"
    assert result.result_json["counters"]["unconfirmed"] == 1


def test_prune_only_selects_jobs_with_explicit_evidence(db_session, settings: Settings) -> None:
    closed = create_job(db_session, title="已下架岗位", company="百度", source_job_id="closed-1")
    closed.status = JobStatus.CLOSED
    closed.archive_evidence_json = {
        "last_closed_evidence": {
            "checked_at": datetime.now(UTC).isoformat(),
            "source_url": closed.source_url,
            "evidence": "页面明确提示「职位已下架」",
        }
    }
    no_evidence = create_job(
        db_session, title="无证据岗位", company="百度", source_job_id="closed-2"
    )
    no_evidence.status = JobStatus.CLOSED
    db_session.commit()

    targets = _service(db_session, settings).prune_targets({})

    assert [job.id for job in targets] == [closed.id]


def test_archive_is_soft_and_keeps_saved_job(db_session, settings: Settings) -> None:
    job = create_job(db_session, title="归档岗位", company="腾讯", source_job_id="archive-1")
    user = _user(db_session, "archive@example.com")
    db_session.add(SavedJob(user_id=user.id, job_id=job.id, list_type="saved"))
    db_session.commit()

    service = _service(db_session, settings)
    service.archive(job, user.id, reason="官方页面确认职位已下架")

    db_session.refresh(job)
    assert job.archived_at is not None
    assert job.archive_reason == "官方页面确认职位已下架"
    assert db_session.query(SavedJob).filter(SavedJob.job_id == job.id).count() == 1
    # Archived jobs leave the default query but stay reachable by id.
    from app.repositories.jobs import JobQuery, JobRepository

    active, total = JobRepository(db_session).list(JobQuery(page=1, page_size=50))
    assert job.id not in [item.id for item in active]
    archived, archived_total = JobRepository(db_session).list(
        JobQuery(page=1, page_size=50, archived=True)
    )
    assert job.id in [item.id for item in archived]
    assert total >= 0 and archived_total >= 1


def test_restore_unarchives_without_claiming_open(db_session, settings: Settings) -> None:
    job = create_job(db_session, title="恢复岗位", company="京东", source_job_id="restore-1")
    job.status = JobStatus.CLOSED
    db_session.commit()
    user = _user(db_session, "restore@example.com")
    service = _service(db_session, settings)
    service.archive(job, user.id, reason="确认下线")

    service.restore(job, user.id)

    db_session.refresh(job)
    assert job.archived_at is None
    assert job.status is JobStatus.CLOSED  # un-archived, still not "open"


def test_consecutive_sweeps_cover_different_jobs(
    db_session, settings: Settings, monkeypatch
) -> None:
    """Two clicks must continue the sweep, not re-check the same newest batch."""

    def fake_read(self, target: Job) -> dict:
        return {
            "status": JobStatus.OPEN,
            "title": target.title,
            "description": target.description,
            "city": target.city,
            "location_text": target.location_text,
            "job_type": target.job_type,
            "evidence": "读到官方详情正文",
        }

    monkeypatch.setattr(JobMaintenanceService, "_read_page", fake_read)

    for index in range(3):
        create_job(db_session, title=f"批量岗位{index}", source_job_id=f"sweep-{index}")

    user = _user(db_session, "sweep@example.com")
    service = _service(db_session, settings)
    options = {"max_jobs": 2, "cooldown_hours": 6}

    first, _ = service.create_run(user, kind="refresh", scope={}, options=options)
    service.execute_refresh(first.id, recheck=True, discover=False)
    second, _ = service.create_run(user, kind="refresh", scope={}, options=options)
    service.execute_refresh(second.id, recheck=True, discover=False)

    first_items = db_session.get(JobMaintenanceRun, first.id).result_json["items"]
    second_items = db_session.get(JobMaintenanceRun, second.id).result_json["items"]
    checked = {item["job_id"] for item in first_items} | {item["job_id"] for item in second_items}

    assert len(first_items) == 2
    assert len(second_items) == 1
    assert len(checked) == 3  # every posting checked exactly once


def test_recently_verified_jobs_are_skipped_by_the_cooldown(
    db_session, settings: Settings, monkeypatch
) -> None:
    job = create_job(db_session, title="刚复核过的岗位", source_job_id="cooldown-1")
    job.last_verified_at = datetime.now(UTC)
    db_session.commit()

    def fail(self, target: Job) -> dict:
        raise AssertionError("冷却期内的岗位不应被复核")

    monkeypatch.setattr(JobMaintenanceService, "_read_page", fail)

    user = _user(db_session, "cooldown@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(user, kind="refresh", scope={}, options={"cooldown_hours": 6})
    service.execute_refresh(run.id, recheck=True, discover=False)

    stored = db_session.get(JobMaintenanceRun, run.id)
    assert stored.result_json["items"] == []


def test_failed_check_stays_eligible_for_the_next_sweep(
    db_session, settings: Settings, monkeypatch
) -> None:
    job = create_job(db_session, title="复核失败岗位", source_job_id="retry-1")

    def boom(self, target: Job) -> dict:
        raise TimeoutError("超时")

    monkeypatch.setattr(JobMaintenanceService, "_read_page", boom)

    user = _user(db_session, "retry@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(user, kind="refresh", scope={}, options={"cooldown_hours": 6})
    service.execute_refresh(run.id, recheck=True, discover=False)

    db_session.refresh(job)
    assert job.last_checked_at is not None
    assert job.last_verified_at is None  # not verified → still selected next time


# ------------------------------------------------------------------------ API
def test_regular_user_cannot_prune_or_read_archive(
    app: FastAPI, settings: Settings, db_session: Session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    create_job(db_session, title="已下架岗位", source_job_id="api-1")

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="plain@example.com")
        prune = client.post("/api/v1/job-maintenance/prune", json={"kind": "prune"})
        archived = client.get("/api/v1/jobs", params={"archived": "true"})
        preview = client.get("/api/v1/job-maintenance/prune-preview")

    assert prune.status_code == 403
    assert archived.status_code == 403
    assert preview.status_code == 403


def test_admin_can_start_prune_and_get_202(
    app: FastAPI, settings: Settings, db_session: Session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="admin@example.com")
        first = client.post("/api/v1/job-maintenance/prune", json={"kind": "prune"})
        second = client.post("/api/v1/job-maintenance/prune", json={"kind": "prune"})

    assert first.status_code == 202, first.text
    body = first.json()["data"]
    assert body["reused"] is False
    UUID(body["run_id"])
    # A repeat click must not start a second crawl.
    assert second.status_code == 202
    assert second.json()["data"]["reused"] is True
    assert second.json()["data"]["run_id"] == body["run_id"]


def test_regular_user_can_start_refresh(app: FastAPI, settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="refresh@example.com")
        response = client.post(
            "/api/v1/job-maintenance",
            json={"kind": "refresh", "recheck": True, "discover": False},
        )

    assert response.status_code == 202, response.text
    assert response.json()["data"]["status"] == "queued"


def test_refresh_requires_at_least_one_option(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="noop@example.com")
        response = client.post(
            "/api/v1/job-maintenance",
            json={"kind": "refresh", "recheck": False, "discover": False},
        )

    assert response.status_code == 422


def test_archived_job_detail_is_still_reachable(
    app: FastAPI, settings: Settings, db_session: Session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    job = create_job(db_session, title="归档可访问", source_job_id="detail-1")
    job.archived_at = datetime.now(UTC)
    db_session.commit()

    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="detail@example.com")
        response = client.get(f"/api/v1/jobs/{job.id}")

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "归档可访问"


def test_activity_reports_a_running_maintenance_run(
    app: FastAPI, settings: Settings, monkeypatch
) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="activity@example.com")
        client.post(
            "/api/v1/job-maintenance",
            json={"kind": "refresh", "recheck": True, "discover": False},
        )
        response = client.get("/api/v1/system/activity")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["job_maintenance"] is not None
    assert data["job_maintenance"]["status"] == "queued"
    assert data["agent"] is None


def test_activity_is_empty_without_background_work(app: FastAPI, settings: Settings) -> None:
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="idle@example.com")
        response = client.get("/api/v1/system/activity")

    assert response.json()["data"] == {"job_maintenance": None, "agent": None}
