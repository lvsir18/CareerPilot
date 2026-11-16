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


def test_latest_run_lets_the_page_resume_after_a_reload(app: FastAPI, settings: Settings) -> None:
    """A discover-only run finishes in seconds; the page must still show it."""
    with AutoCsrfTestClient(app, settings) as client:
        register_user(client, email="latest-run@example.com")

        assert client.get("/api/v1/job-maintenance/latest").json()["data"] is None

        created = client.post(
            "/api/v1/job-maintenance",
            json={"kind": "discover", "recheck": False, "discover": True},
        )
        run_id = created.json()["data"]["run_id"]

        latest = client.get("/api/v1/job-maintenance/latest").json()["data"]

    assert latest["id"] == run_id
    assert latest["kind"] == "discover"
    assert latest["status"] in {"queued", "running"}


def test_discover_depth_maps_to_per_company_and_keywords(
    db_session: Session, settings: Settings, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "job_discover_keywords", "大模型,算法,后端,前端,数据")
    monkeypatch.setattr(settings, "job_discover_max_keywords", 10)
    monkeypatch.setattr(settings, "job_discover_max_per_company", 100)
    service = JobMaintenanceService(db_session, settings)

    quick = service._discover_plan({}, {"discover_depth": "quick"})
    standard = service._discover_plan({}, {"discover_depth": "standard"})
    deep = service._discover_plan({}, {"discover_depth": "deep"})

    assert quick == (10, [None])
    assert standard == (30, [None, "大模型", "算法"])
    assert deep[0] == 50
    assert deep[1] == [None, "大模型", "算法", "后端", "前端", "数据"]


def test_explicit_query_wins_over_the_keyword_matrix(
    db_session: Session, settings: Settings
) -> None:
    service = JobMaintenanceService(db_session, settings)

    _, queries = service._discover_plan({"q": "大模型"}, {"discover_depth": "deep"})

    assert queries == ["大模型"]


def test_depth_budget_is_capped_by_configuration(
    db_session: Session, settings: Settings, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "job_discover_max_per_company", 20)
    monkeypatch.setattr(settings, "job_discover_max_keywords", 2)
    service = JobMaintenanceService(db_session, settings)

    per_company, queries = service._discover_plan({}, {"discover_depth": "deep"})

    assert per_company == 20
    assert len(queries) == 2


def test_recheck_keeps_the_stored_title_when_the_page_title_is_a_site_name(
    db_session, settings: Settings, monkeypatch
) -> None:
    """SPA pages report "京东校招" as document title; that must not rename a job."""
    job = create_job(db_session, title="算法工程师-数据挖掘", source_job_id="jd-title-1")

    def fake_read(self, target: Job) -> dict:
        return {
            "status": JobStatus.OPEN,
            "title": "京东校招",
            "description": "工作内容：负责数据挖掘。" * 20,
            "city": None,
            "location_text": None,
            "job_type": None,
            "evidence": "读到官方详情正文",
        }

    monkeypatch.setattr(JobMaintenanceService, "_read_page", fake_read)

    JobMaintenanceService(db_session, settings)._recheck_one(job)

    db_session.refresh(job)
    assert job.title == "算法工程师-数据挖掘"
    assert len(job.description or "") > 100


def test_verify_leads_run_covers_pending_candidates_of_a_company(
    db_session, settings: Settings, monkeypatch
) -> None:
    """One click verifies every pending candidate; one failure must not stop it."""
    from types import SimpleNamespace

    from app.core.errors import AppError
    from app.db.models.enums import JobSourceMethod, LeadVerificationStatus
    from app.db.models.job import Company
    from app.db.models.job_lead import JobLead
    from app.services.job_lead_service import JobLeadService

    company = Company(name="阿里巴巴", normalized_name="阿里巴巴-verify-leads")
    db_session.add(company)
    db_session.flush()
    good = JobLead(
        company_id=company.id,
        title="可核验候选",
        official_url="https://campus-talent.alibaba.com/campus/position/1",
        source_method=JobSourceMethod.SEARCH_DISCOVERY,
        verification_status=LeadVerificationStatus.SEARCH_SNIPPET_ONLY,
        dedupe_key="verify-leads-1",
    )
    bad = JobLead(
        company_id=company.id,
        title="不可核验候选",
        official_url="https://campus-talent.alibaba.com/campus/position/2",
        source_method=JobSourceMethod.SEARCH_DISCOVERY,
        verification_status=LeadVerificationStatus.USER_PROVIDED,
        dedupe_key="verify-leads-2",
    )
    db_session.add_all([good, bad])
    db_session.commit()

    def fake_verify(self, lead_id, user_id):
        if lead_id == good.id:
            return SimpleNamespace(title=good.title), None
        raise AppError("INVALID_SOURCE_URL", "该链接不是可信职位详情页", status_code=422)

    monkeypatch.setattr(JobLeadService, "_verify_lead", fake_verify)

    user = _user(db_session, "verify-leads@example.com")
    service = _service(db_session, settings)
    run, created = service.create_run(
        user,
        kind="verify_leads",
        scope={"companies": ["阿里巴巴"]},
        options={"limit": 10},
    )
    assert created is True

    service.execute_verify_leads(run.id)

    stored = db_session.get(JobMaintenanceRun, run.id)
    counters = stored.result_json["counters"]
    assert stored.status == "partial"
    assert counters["verified"] == 1
    assert counters["failed"] == 1
    outcomes = {item["lead_id"]: item["outcome"] for item in stored.result_json["items"]}
    assert outcomes[str(good.id)] == "verified"
    assert outcomes[str(bad.id)] == "failed"


def test_pending_lead_count_ignores_verified_and_other_users(
    db_session, settings: Settings
) -> None:
    from app.db.models.enums import JobSourceMethod, LeadVerificationStatus
    from app.db.models.job import Company
    from app.db.models.job_lead import JobLead

    company = Company(name="阿里巴巴", normalized_name="阿里巴巴-pending-count")
    db_session.add(company)
    db_session.flush()
    owner = _user(db_session, "pending-owner@example.com")
    other = _user(db_session, "pending-other@example.com")

    db_session.add_all(
        [
            JobLead(
                company_id=company.id,
                title="公共候选",
                official_url="https://campus-talent.alibaba.com/campus/position/10",
                source_method=JobSourceMethod.SEARCH_DISCOVERY,
                verification_status=LeadVerificationStatus.SEARCH_SNIPPET_ONLY,
                dedupe_key="pc-1",
            ),
            JobLead(
                company_id=company.id,
                title="自己的导入",
                owner_user_id=owner.id,
                official_url="https://campus-talent.alibaba.com/campus/position/11",
                source_method=JobSourceMethod.MANUAL_IMPORT,
                verification_status=LeadVerificationStatus.USER_PROVIDED,
                dedupe_key="pc-2",
            ),
            JobLead(
                company_id=company.id,
                title="别人的导入",
                owner_user_id=other.id,
                official_url="https://campus-talent.alibaba.com/campus/position/12",
                source_method=JobSourceMethod.MANUAL_IMPORT,
                verification_status=LeadVerificationStatus.USER_PROVIDED,
                dedupe_key="pc-3",
            ),
            JobLead(
                company_id=company.id,
                title="已核验",
                official_url="https://campus-talent.alibaba.com/campus/position/13",
                source_method=JobSourceMethod.SEARCH_DISCOVERY,
                verification_status=LeadVerificationStatus.VERIFIED_OFFICIAL,
                dedupe_key="pc-4",
            ),
        ]
    )
    db_session.commit()

    count = _service(db_session, settings).pending_lead_count(owner.id, ["阿里巴巴"])

    assert count == 2  # public + own, excluding other users' and verified ones


def test_cancel_closes_a_run_left_running_by_a_dead_worker(db_session, settings: Settings) -> None:
    """A container restart leaves runs in `running`; cancel must clean them up."""
    user = _user(db_session, "cancel-zombie@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(user, kind="refresh", scope={}, options={"max_jobs": 1})
    run.status = "running"
    run.started_at = datetime.now(UTC) - __import__("datetime").timedelta(minutes=30)
    db_session.commit()

    cancelled = service.cancel(run.id)

    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    assert cancelled.cancel_requested_at is not None


def _make_leads(db_session, count: int, company_name: str, prefix: str) -> None:
    from sqlalchemy import select as sa_select

    from app.db.models.enums import JobSourceMethod, LeadVerificationStatus
    from app.db.models.job import Company
    from app.db.models.job_lead import JobLead

    company = db_session.scalar(sa_select(Company).where(Company.name == company_name))
    if company is None:
        company = Company(name=company_name, normalized_name=f"{company_name}-{prefix}")
        db_session.add(company)
        db_session.flush()
    for index in range(count):
        db_session.add(
            JobLead(
                company_id=company.id,
                title=f"{prefix}-{index}",
                official_url=f"https://campus-talent.alibaba.com/campus/position/{prefix}{index}",
                source_method=JobSourceMethod.SEARCH_DISCOVERY,
                verification_status=LeadVerificationStatus.SEARCH_SNIPPET_ONLY,
                dedupe_key=f"{prefix}-{index}",
            )
        )
    db_session.commit()


def test_verify_leads_without_limit_covers_every_pending_candidate(
    db_session, settings: Settings, monkeypatch
) -> None:
    """「全选」must not be quietly capped by the old 200-item bound."""
    from types import SimpleNamespace

    from app.services.job_lead_service import JobLeadService

    _make_leads(db_session, 3, "阿里巴巴", "all")
    monkeypatch.setattr(
        JobLeadService,
        "_verify_lead",
        lambda self, lead_id, user_id: (SimpleNamespace(title="x"), None),
    )

    user = _user(db_session, "verify-all@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(
        user, kind="verify_leads", scope={"companies": ["阿里巴巴"]}, options={}
    )
    service.execute_verify_leads(run.id)

    stored = db_session.get(JobMaintenanceRun, run.id)
    assert stored.progress_json["total"] == 3
    assert stored.result_json["counters"]["verified"] == 3


def test_verify_leads_limit_caps_the_batch(db_session, settings: Settings, monkeypatch) -> None:
    from types import SimpleNamespace

    from app.services.job_lead_service import JobLeadService

    _make_leads(db_session, 3, "阿里巴巴", "cap")
    monkeypatch.setattr(
        JobLeadService,
        "_verify_lead",
        lambda self, lead_id, user_id: (SimpleNamespace(title="x"), None),
    )

    user = _user(db_session, "verify-cap@example.com")
    service = _service(db_session, settings)
    run, _ = service.create_run(
        user, kind="verify_leads", scope={"companies": ["阿里巴巴"]}, options={"limit": 2}
    )
    service.execute_verify_leads(run.id)

    stored = db_session.get(JobMaintenanceRun, run.id)
    assert stored.progress_json["total"] == 2
    assert len(stored.result_json["items"]) == 2
