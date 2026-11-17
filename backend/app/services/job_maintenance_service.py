"""Job library maintenance: refresh existing postings, discover new ones, prune closed.

Design rules (also documented in AGENTS.md):

- Only an explicit closure statement from the official page may close a posting.
  Timeouts, login walls, redirects, empty bodies and 404s are *unconfirmed*.
- Archiving is a soft delete: saved jobs, applications and match history stay.
- Every batch is persisted in ``job_maintenance_runs`` so the UI can resume
  progress after a reload, and a repeated click reuses the active run.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.connectors.meituan_detail import fetch_detail
from app.connectors.rendered_page import RenderedPageReader
from app.connectors.schemas import RawJob
from app.connectors.tencent_campus import TencentCampusConnector
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.enums import JobStatus, LeadVerificationStatus, VerificationStatus
from app.db.models.job import Company, Job
from app.db.models.job_lead import JobLead
from app.db.models.job_maintenance import JobMaintenanceRun
from app.db.models.user import User
from app.repositories.jobs import JobQuery, JobRepository
from app.search.domains import COMPANY_NAMES, resolve_company
from app.services.job_ingestion import compute_content_hash
from app.services.job_lead_service import JobLeadService
from app.services.official_jobs_service import OfficialJobsService

logger = get_logger(__name__)

ACTIVE_STATUSES = ("queued", "running")

# (per company, keyword budget): deeper sweeps cost more crawling time.
_DISCOVER_DEPTHS: dict[str, tuple[int, int]] = {
    "quick": (10, 1),
    "standard": (30, 3),
    "deep": (50, 6),
}

# A maintenance sweep may now cover a large slice of the library; the cooldown
# below is what keeps repeated clicks from re-crawling the same postings.
MAX_JOBS_PER_RUN = 200
MAX_DISCOVER_COMPANIES = 6
MAX_DISCOVER_PER_COMPANY = 10
PRUNE_SCAN_LIMIT = 300
MAX_ARCHIVE_PER_RUN = 100
# Skip postings verified within this window by default; 0 disables the cooldown.
DEFAULT_COOLDOWN_HOURS = 6
MAX_COOLDOWN_HOURS = 168
# One click verifies at most this many candidate links (each opens a page).
MAX_LEAD_VERIFY_PER_RUN = 1000
# ``limit=None`` on a verify run means "every pending candidate".
# One candidate link may open a browser page; cap it so a hang cannot stall the batch.
LEAD_VERIFY_TIMEOUT_SECONDS = 90

# Result vocabulary shared with the API/UI. "unchanged" (checked, nothing new)
# and "unconfirmed" (could not check) must never be merged.
OUTCOME_CREATED = "created"
OUTCOME_UPDATED = "updated"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_CLOSED = "closed"
OUTCOME_REOPENED = "reopened"
OUTCOME_UNCONFIRMED = "unconfirmed"
OUTCOME_UNSUPPORTED = "unsupported"
OUTCOME_ARCHIVED = "archived"

_COUNTER_KEYS = (
    OUTCOME_CREATED,
    OUTCOME_UPDATED,
    OUTCOME_UNCHANGED,
    OUTCOME_CLOSED,
    OUTCOME_REOPENED,
    OUTCOME_UNCONFIRMED,
    OUTCOME_UNSUPPORTED,
    OUTCOME_ARCHIVED,
)


# Page titles leak into job titles when a site uses one document title for all
# postings ("职位详情 | 美团招聘"). Those must be replaced by the real name.
_SITE_TITLE_MARKERS = ("职位详情", "美团招聘", "招聘官网", "京东校招", "校园招聘官网")


def _pick_title(current: str | None, incoming: str | None) -> str:
    if not current:
        return (incoming or "")[:300]
    if any(marker in current for marker in _SITE_TITLE_MARKERS) and incoming:
        return incoming[:300]
    return current[:300]


def _scope_query(
    scope: dict[str, Any],
    *,
    archived: bool = False,
    status: JobStatus | None = None,
    page_size: int = MAX_JOBS_PER_RUN,
    page: int = 1,
    include_demo: bool = False,
    last_verified_before: datetime | None = None,
    sort: str = "first_seen_at_desc",
) -> JobQuery:
    return JobQuery(
        q=(scope.get("q") or None),
        companies=[str(item) for item in scope.get("companies") or [] if item],
        cities=[str(item) for item in scope.get("cities") or [] if item],
        job_types=[str(item) for item in scope.get("job_types") or [] if item],
        source_types=[str(item) for item in scope.get("source_types") or [] if item],
        recruitment_programs=[
            str(item) for item in scope.get("recruitment_programs") or [] if item
        ],
        status=status,
        archived=archived,
        last_verified_before=last_verified_before,
        page=page,
        page_size=page_size,
        include_demo=include_demo,
        sort=sort,
    )


def _dedupe_key(kind: str, scope: dict[str, Any], options: dict[str, Any]) -> str:
    material = json.dumps(
        {"kind": kind, "scope": scope, "options": options},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


@contextmanager
def _time_limit(seconds: int):
    """Raise inside the block after ``seconds`` (worker tasks run on the main thread)."""
    import signal

    def _raise(signum, frame):
        raise TimeoutError(f"单条处理超过 {seconds} 秒")

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class JobMaintenanceService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repository = JobRepository(session)

    # ------------------------------------------------------------- run records
    def create_run(
        self,
        user: User,
        *,
        kind: str,
        scope: dict[str, Any],
        options: dict[str, Any],
    ) -> tuple[JobMaintenanceRun, bool]:
        """Create a run, or return the still-active one with the same request."""
        if kind not in {"refresh", "discover", "prune", "verify_leads"}:
            raise AppError("INVALID_KIND", "不支持的任务类型", status_code=422)
        key = _dedupe_key(kind, scope, options)
        active = self._session.scalar(
            select(JobMaintenanceRun)
            .where(
                JobMaintenanceRun.dedupe_key == key,
                JobMaintenanceRun.status.in_(ACTIVE_STATUSES),
            )
            .order_by(JobMaintenanceRun.created_at.desc())
            .limit(1)
        )
        if active is not None:
            return active, False
        run = JobMaintenanceRun(
            user_id=user.id,
            kind=kind,
            status="queued",
            dedupe_key=key,
            scope_json=scope,
            options_json=options,
            progress_json={"total": 0, "processed": 0, "counters": dict.fromkeys(_COUNTER_KEYS, 0)},
            result_json={},
        )
        self._session.add(run)
        self._session.commit()
        self._session.refresh(run)
        return run, True

    def get_run(self, run_id: UUID) -> JobMaintenanceRun:
        run = self._session.get(JobMaintenanceRun, run_id)
        if run is None:
            raise AppError("MAINTENANCE_NOT_FOUND", "任务不存在", status_code=404)
        return run

    def latest_active_run(self, kind: str) -> JobMaintenanceRun | None:
        return self._session.scalar(
            select(JobMaintenanceRun)
            .where(
                JobMaintenanceRun.kind == kind,
                JobMaintenanceRun.status.in_(ACTIVE_STATUSES),
            )
            .order_by(JobMaintenanceRun.created_at.desc())
            .limit(1)
        )

    def latest_run_for_user(
        self, user_id: UUID, kinds: tuple[str, ...] = ("refresh", "discover")
    ) -> JobMaintenanceRun | None:
        """Newest run of this user in any status, so the page can resume/replay it."""
        return self._session.scalar(
            select(JobMaintenanceRun)
            .where(
                JobMaintenanceRun.user_id == user_id,
                JobMaintenanceRun.kind.in_(kinds),
            )
            .order_by(JobMaintenanceRun.created_at.desc())
            .limit(1)
        )

    def claim(self, run_id: UUID) -> JobMaintenanceRun | None:
        """Atomically take a queued run. A duplicate dispatch must be a no-op."""
        run = self._session.scalar(
            select(JobMaintenanceRun).where(JobMaintenanceRun.id == run_id).with_for_update()
        )
        if run is None or run.status != "queued":
            return None
        run.status = "running"
        run.started_at = datetime.now(UTC)
        self._session.commit()
        return run

    def set_progress(
        self,
        run_id: UUID,
        *,
        total: int | None = None,
        processed: int | None = None,
        counters: dict[str, int] | None = None,
        current: str | None = None,
    ) -> None:
        run = self._session.get(JobMaintenanceRun, run_id)
        if run is None:
            return
        progress = dict(run.progress_json or {})
        if total is not None:
            progress["total"] = total
        if processed is not None:
            progress["processed"] = processed
        if counters is not None:
            progress["counters"] = counters
        if current is not None:
            progress["current"] = current
        run.progress_json = progress
        self._session.commit()

    def finish(
        self,
        run_id: UUID,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        run = self._session.get(JobMaintenanceRun, run_id)
        if run is None:
            return
        run.status = status
        run.finished_at = datetime.now(UTC)
        if result is not None:
            run.result_json = result
        if error is not None:
            run.error_message = error[:2000]
        self._session.commit()

    def cancel(self, run_id: UUID) -> JobMaintenanceRun:
        """Stop a run immediately.

        The cooperative flag alone cannot clean up a run whose worker died (a
        container restart leaves it ``running`` forever), so cancel also closes
        the row. A live worker still sees ``cancel_requested_at`` and stops at
        the next item.
        """
        run = self.get_run(run_id)
        if run.status in ACTIVE_STATUSES:
            now = datetime.now(UTC)
            run.cancel_requested_at = now
            run.status = "cancelled"
            run.finished_at = now
            run.error_message = run.error_message or "已取消"
            self._session.commit()
        return run

    def is_cancel_requested(self, run_id: UUID) -> bool:
        run = self._session.get(JobMaintenanceRun, run_id, populate_existing=True)
        return run is not None and run.cancel_requested_at is not None

    # ---------------------------------------------------------------- previews
    def scope_total(self, scope: dict[str, Any]) -> int:
        query = _scope_query(scope, page_size=1, include_demo=self._settings.demo_mode)
        _jobs, total = self._repository.list(query)
        return total

    def prune_targets(self, scope: dict[str, Any]) -> list[Job]:
        """Only postings with an explicit closure record are prune candidates."""
        query = _scope_query(
            scope,
            status=JobStatus.CLOSED,
            page_size=PRUNE_SCAN_LIMIT,
            include_demo=self._settings.demo_mode,
        )
        jobs, _total = self._repository.list(query)
        return [job for job in jobs if self._closure_evidence(job) is not None]

    def prune_preview(self, scope: dict[str, Any]) -> dict[str, Any]:
        targets = self.prune_targets(scope)
        return {
            "count": len(targets),
            "items": [self._item(job) for job in targets[:MAX_ARCHIVE_PER_RUN]],
            "truncated": len(targets) > MAX_ARCHIVE_PER_RUN,
        }

    # ------------------------------------------------------------------ worker
    def execute_refresh(self, run_id: UUID, *, recheck: bool, discover: bool) -> dict[str, Any]:
        run = self.claim(run_id)
        if run is None:
            return {"status": "skipped"}
        scope = dict(run.scope_json or {})
        options = dict(run.options_json or {})
        counters = dict.fromkeys(_COUNTER_KEYS, 0)
        items: list[dict[str, Any]] = []
        unsupported: list[dict[str, str]] = []

        # Re-check only what the current filter actually covers, newest first.
        targets: list[Job] = []
        if recheck:
            cooldown_hours = self._cooldown_hours(options)
            cutoff = (
                datetime.now(UTC) - timedelta(hours=cooldown_hours) if cooldown_hours > 0 else None
            )
            query = _scope_query(
                scope,
                page_size=self._limit(options.get("max_jobs", MAX_JOBS_PER_RUN)),
                include_demo=self._settings.demo_mode,
                last_verified_before=cutoff,
                # Least recently checked first: a second click must continue the
                # sweep instead of re-checking the same newest batch.
                sort="last_checked_asc",
            )
            targets, _total = self._repository.list(query)
        total = len(targets)
        self.set_progress(run_id, total=total, processed=0, counters=counters)

        for index, job in enumerate(targets, start=1):
            if self.is_cancel_requested(run_id):
                self.finish(
                    run_id, status="cancelled", result=self._result(items, counters, unsupported)
                )
                return {"status": "cancelled"}
            item = self._recheck_one(job)
            items.append(item)
            counters[item["outcome"]] = counters.get(item["outcome"], 0) + 1
            self.set_progress(
                run_id,
                total=total,
                processed=index,
                counters=counters,
                current=f"{item.get('company') or ''} · {item.get('title') or ''}".strip(" ·"),
            )

        if discover and not self.is_cancel_requested(run_id):
            per_company, queries = self._discover_plan(scope, options)
            seen: set[tuple[str, str]] = set()
            for query in queries:
                if self.is_cancel_requested(run_id):
                    break
                label = query or "最新发布"
                # Reported per query so the panel shows what is being fetched now.
                self.set_progress(
                    run_id,
                    total=total,
                    processed=len(items),
                    counters=counters,
                    current=f"发现新增 · {label}",
                )
                found = self._discover(
                    scope,
                    unsupported,
                    keyword=query,
                    per_company=per_company,
                    seen=seen,
                )
                items.extend(found)
                for item in found:
                    counters[item["outcome"]] = counters.get(item["outcome"], 0) + 1
                total += len(found)
            counters[OUTCOME_UNSUPPORTED] = len(unsupported)
            self.set_progress(
                run_id, total=total, processed=total, counters=counters, current="发现新增完成"
            )

        failed = len([item for item in items if item["outcome"] == OUTCOME_UNCONFIRMED])
        status = "success" if failed == 0 else "partial"
        self.finish(run_id, status=status, result=self._result(items, counters, unsupported))
        return {"status": status, "counters": counters}

    def pending_lead_count(self, user_id: UUID, companies: list[str]) -> int:
        """How many candidate links a one-click verification would process."""
        return len(self._pending_leads(user_id, {"companies": companies}, limit=None))

    def _pending_leads(
        self, user_id: UUID, scope: dict[str, Any], *, limit: int | None
    ) -> list[JobLead]:
        """Candidates this account may verify: public ones plus its own imports."""
        from app.search.domains import resolve_company

        stmt = (
            select(JobLead)
            .where(
                JobLead.verification_status != LeadVerificationStatus.VERIFIED_OFFICIAL,
                or_(
                    JobLead.owner_user_id.is_(None),
                    JobLead.owner_user_id == user_id,
                ),
            )
            .order_by(JobLead.first_seen_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        requested = [
            str(name).strip() for name in scope.get("companies") or [] if str(name).strip()
        ]
        if requested:
            labels = []
            for name in requested:
                key = resolve_company(name)
                labels.append(COMPANY_NAMES.get(key, name) if key else name)
            stmt = stmt.join(Company, Company.id == JobLead.company_id).where(
                Company.name.in_(labels)
            )
        return list(self._session.scalars(stmt))

    def execute_verify_leads(self, run_id: UUID) -> dict[str, Any]:
        """Verify every pending candidate link of the selected companies.

        Runs in the worker, so it is not bound by the per-minute limiter that
        protects the interactive "verify" button.
        """
        run = self.claim(run_id)
        if run is None:
            return {"status": "skipped"}
        scope = dict(run.scope_json or {})
        options = dict(run.options_json or {})
        # ``None`` = every pending candidate of these companies; a number caps it.
        raw_limit = options.get("limit")
        limit = (
            None
            if raw_limit in (None, "")
            else max(1, min(int(raw_limit), MAX_LEAD_VERIFY_PER_RUN))
        )
        targets = self._pending_leads(run.user_id, scope, limit=limit)
        total = len(targets)
        counters: dict[str, int] = {"verified": 0, "failed": 0}
        self.set_progress(
            run_id, total=total, processed=0, counters=counters, current="准备核验候选"
        )

        service = JobLeadService(self._session, self._settings)
        items: list[dict[str, Any]] = []
        for index, lead in enumerate(targets, start=1):
            if self.is_cancel_requested(run_id):
                self.finish(
                    run_id,
                    status="cancelled",
                    result={"items": items, "counters": counters},
                )
                return {"status": "cancelled"}
            try:
                # A single unreachable page must not freeze the batch.
                with _time_limit(LEAD_VERIFY_TIMEOUT_SECONDS):
                    service._verify_lead(lead.id, run.user_id)
                counters["verified"] += 1
                items.append(
                    {
                        "lead_id": str(lead.id),
                        "company": lead.company.name if lead.company else None,
                        "title": lead.title,
                        "outcome": "verified",
                        "reason": None,
                    }
                )
            except AppError as exc:
                counters["failed"] += 1
                items.append(
                    {
                        "lead_id": str(lead.id),
                        "company": lead.company.name if lead.company else None,
                        "title": lead.title,
                        "outcome": "failed",
                        "reason": f"{exc.code}: {exc.message}"[:200],
                    }
                )
            except Exception as exc:
                counters["failed"] += 1
                items.append(
                    {
                        "lead_id": str(lead.id),
                        "company": lead.company.name if lead.company else None,
                        "title": lead.title,
                        "outcome": "failed",
                        "reason": f"{type(exc).__name__}: {exc}"[:200],
                    }
                )
            self.set_progress(
                run_id,
                total=total,
                processed=index,
                counters=counters,
                current=str(lead.title or "")[:80],
            )

        status = "success" if counters["failed"] == 0 else "partial"
        self.finish(run_id, status=status, result={"items": items, "counters": counters})
        return {"status": status, "counters": counters}

    def execute_prune(self, run_id: UUID) -> dict[str, Any]:
        run = self.claim(run_id)
        if run is None:
            return {"status": "skipped"}
        scope = dict(run.scope_json or {})
        targets = self.prune_targets(scope)[:MAX_ARCHIVE_PER_RUN]
        counters = dict.fromkeys(_COUNTER_KEYS, 0)
        items: list[dict[str, Any]] = []
        self.set_progress(run_id, total=len(targets), processed=0, counters=counters)
        for index, job in enumerate(targets, start=1):
            if self.is_cancel_requested(run_id):
                self.finish(run_id, status="cancelled", result=self._result(items, counters, []))
                return {"status": "cancelled"}
            item = self.archive(job, run.user_id, reason="官方页面确认职位已下架")
            items.append(item)
            counters[OUTCOME_ARCHIVED] += 1
            self.set_progress(run_id, total=len(targets), processed=index, counters=counters)
        self.finish(run_id, status="success", result=self._result(items, counters, []))
        return {"status": "success", "counters": counters}

    # ----------------------------------------------------------------- recheck
    def _recheck_one(self, job: Job) -> dict[str, Any]:
        now = datetime.now(UTC)
        source_type = job.source.source_type if job.source else ""
        snapshot: dict[str, Any]
        try:
            if source_type == "tencent_campus":
                snapshot = self._read_tencent(job)
            else:
                snapshot = self._read_page(job)
        except Exception as exc:
            logger.warning(
                "job_recheck_unconfirmed",
                extra={"job_id": str(job.id), "error": f"{type(exc).__name__}: {exc}"[:300]},
            )
            job.last_checked_at = now
            self._session.commit()
            return {
                **self._item(job),
                "outcome": OUTCOME_UNCONFIRMED,
                "reason": f"{type(exc).__name__}: {exc}"[:300],
            }

        status = snapshot["status"]
        evidence = snapshot.get("evidence")
        if status == JobStatus.UNKNOWN:
            job.last_checked_at = now
            self._session.commit()
            return {**self._item(job), "outcome": OUTCOME_UNCONFIRMED, "reason": evidence}

        outcome = self._apply_snapshot(job, snapshot, now)
        if outcome == OUTCOME_REOPENED:
            evidence = f"重新读到官方详情（{(evidence or '')[:120]}）"
        return {**self._item(job), "outcome": outcome, "reason": evidence}

    def _read_page(self, job: Job) -> dict[str, Any]:
        # Meituan exposes the same detail as JSON; its document.title is the site
        # name, so scraping the DOM produced jobs literally titled
        # "职位详情 | 美团招聘".
        if "meituan.com" in job.source_url:
            detail = fetch_detail(self._settings, job.source_url)
            if detail:
                return {
                    "status": JobStatus.OPEN,
                    "title": detail["title"],
                    "description": detail["description"],
                    "city": detail["city"],
                    "location_text": detail["location_text"],
                    "job_type": detail["job_type"],
                    "department": detail["department"],
                    "published_at": detail["published_at"],
                    "recruitment_program": None,
                    "requirements": detail["requirements"],
                    "evidence": "美团官方详情接口",
                }
        reader = RenderedPageReader(self._settings)
        ok, message = reader.available()
        if not ok:
            raise AppError("RENDER_UNAVAILABLE", message, status_code=503)
        page = reader.read(job.source_url)
        return {
            "status": page.status,
            "title": page.title,
            "description": page.description,
            "city": page.city,
            "location_text": page.location_text,
            "job_type": page.job_type,
            # Labels the page shows next to the JD (在招业务 / 更新于 …).
            "department": page.department,
            "published_at": page.published_at,
            "recruitment_program": page.recruitment_program,
            "evidence": page.status_evidence,
        }

    def _read_tencent(self, job: Job) -> dict[str, Any]:
        connector = TencentCampusConnector(self._settings)
        try:
            payload = connector.detail(job.source_job_id)
            raw = connector.to_raw_job(payload)
        finally:
            connector.close()
        return {
            "status": JobStatus.OPEN,
            "title": raw.title,
            "description": raw.description,
            "city": raw.city,
            "location_text": raw.location_text,
            "job_type": raw.job_type,
            "evidence": "腾讯校招接口返回该岗位详情",
        }

    def _apply_snapshot(self, job: Job, snapshot: dict[str, Any], now: datetime) -> str:
        status: JobStatus = snapshot["status"]
        if status == JobStatus.CLOSED:
            job.status = JobStatus.CLOSED
            job.last_checked_at = now
            job.last_verified_at = now
            evidence = {
                "checked_at": now.isoformat(),
                "source_url": job.source_url,
                "evidence": snapshot.get("evidence"),
            }
            job.archive_evidence_json = {
                **(job.archive_evidence_json or {}),
                "last_closed_evidence": evidence,
            }
            self._session.commit()
            return OUTCOME_CLOSED

        company = job.company.name if job.company else ""
        raw = RawJob(
            source_type=job.source.source_type if job.source else "official",
            source_key=job.source.source_key if job.source else "official",
            source_job_id=job.source_job_id,
            company=company or job.title,
            # SPA pages report the site name as their document title ("京东校招"),
            # not the posting. Keep the stored title and only fill a blank one.
            title=_pick_title(job.title, snapshot.get("title")),
            source_url=job.source_url,
            description=snapshot.get("description"),
            department=snapshot.get("department") or job.department,
            recruitment_program=snapshot.get("recruitment_program") or job.recruitment_program,
            published_at=snapshot.get("published_at") or job.published_at,
            location_text=snapshot.get("location_text") or job.location_text,
            city=snapshot.get("city") or job.city,
            job_type=snapshot.get("job_type") or job.job_type,
            requirements=snapshot.get("requirements") or job.requirements_json or [],
            fetched_at=now,
            status=JobStatus.OPEN,
            verification_status=VerificationStatus.VERIFIED,
            verified_at=now,
        )
        new_hash = compute_content_hash(raw)
        changed = new_hash != job.content_hash
        if changed:
            job.title = raw.title
            job.description = raw.description
            job.location_text = raw.location_text
            job.city = raw.city
            job.job_type = raw.job_type
            # 部门/招聘项目/发布时间 also come from the page labels now.
            job.department = raw.department
            job.recruitment_program = raw.recruitment_program
            job.published_at = raw.published_at
            job.content_hash = new_hash
        job.last_checked_at = now
        job.last_verified_at = now
        job.verification_status = VerificationStatus.VERIFIED
        job.verified_at = now
        reopened = job.status == JobStatus.CLOSED
        job.status = JobStatus.OPEN
        if job.archived_at is not None:
            # Explicit "still open" evidence is the only thing that restores it.
            job.archived_at = None
            job.archived_by_user_id = None
            job.archive_reason = None
            reopened = True
        self._session.commit()
        if reopened:
            return OUTCOME_REOPENED
        return OUTCOME_UPDATED if changed else OUTCOME_UNCHANGED

    # ----------------------------------------------------------------- discover
    def _discover_plan(
        self, scope: dict[str, Any], options: dict[str, Any]
    ) -> tuple[int, list[str | None]]:
        """How many postings per company, and which keyword queries to run.

        ``None`` means "no keyword" — the newest page of the official list.
        A query from the page filter wins over the keyword matrix.
        """
        depth = str(options.get("discover_depth") or "standard")
        per_company, keyword_budget = _DISCOVER_DEPTHS.get(depth, _DISCOVER_DEPTHS["standard"])
        per_company = max(1, min(per_company, self._settings.job_discover_max_per_company))
        explicit = (scope.get("q") or "").strip()
        if explicit:
            return per_company, [explicit]
        keywords = [
            item.strip()
            for item in (self._settings.job_discover_keywords or "").split(",")
            if item.strip()
        ]
        budget = max(1, min(keyword_budget, self._settings.job_discover_max_keywords))
        return per_company, [None, *keywords[: budget - 1]]

    def _discover(
        self,
        scope: dict[str, Any],
        unsupported: list[dict[str, str]],
        *,
        keyword: str | None,
        per_company: int,
        seen: set[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        catalogue = OfficialJobsService(self._session, self._settings).supported()
        supported_keys = [item["key"] for item in catalogue if item.get("supported")]
        labels = {item["key"]: item["label"] for item in catalogue}

        requested = [resolve_company(str(name)) for name in scope.get("companies") or []]
        keys = [key for key in requested if key]
        if not keys:
            keys = supported_keys[:MAX_DISCOVER_COMPANIES]
        keys = [key for key in dict.fromkeys(keys) if key in supported_keys][
            :MAX_DISCOVER_COMPANIES
        ]
        for value in scope.get("companies") or []:
            if resolve_company(str(value)) is None:
                unsupported.append({"name": str(value), "reason": "暂不支持自动发现"})

        service = OfficialJobsService(self._session, self._settings)
        try:
            result = service.search(
                companies=keys,
                keyword=keyword,
                limit=per_company,
            )
        except AppError as exc:
            unsupported.append(
                {"name": "、".join(labels.get(key, key) for key in keys), "reason": exc.message}
            )
            return []

        items: list[dict[str, Any]] = []
        for row in result.get("companies") or []:
            if row.get("error"):
                unsupported.append({"name": row.get("label") or row["key"], "reason": row["error"]})
        for job in result.get("jobs") or []:
            # The keyword matrix re-reads overlapping postings; report each once.
            dedupe = (
                str(job.get("company") or ""),
                str(job.get("source_url") or job.get("title") or ""),
            )
            if dedupe in seen:
                continue
            seen.add(dedupe)
            outcome = job.get("outcome") or OUTCOME_CREATED
            if outcome not in {OUTCOME_CREATED, OUTCOME_UPDATED, OUTCOME_UNCHANGED}:
                outcome = OUTCOME_CREATED
            items.append(
                {
                    "job_id": None,
                    "company": job.get("company"),
                    "title": job.get("title"),
                    "city": job.get("city"),
                    "outcome": outcome,
                    "reason": "官方直连发现并写入",
                }
            )
        return items

    # -------------------------------------------------------------------- prune
    def archive(self, job: Job, user_id: UUID | None, *, reason: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        job.archived_at = now
        job.archived_by_user_id = user_id
        job.archive_reason = reason[:200]
        job.archive_evidence_json = {
            **(job.archive_evidence_json or {}),
            "archived_at": now.isoformat(),
            "reason": reason,
        }
        self._session.commit()
        return {**self._item(job), "outcome": OUTCOME_ARCHIVED, "reason": reason}

    def restore(self, job: Job, user_id: UUID | None) -> dict[str, Any]:
        """Un-archive only. It does not claim the posting is open again."""
        job.archived_at = None
        job.archived_by_user_id = user_id
        job.archive_reason = None
        self._session.commit()
        return {**self._item(job), "outcome": "restored"}

    # ------------------------------------------------------------------ helpers
    def get_job(self, job_id: UUID) -> Job:
        job = self._session.scalar(
            select(Job)
            .options(joinedload(Job.company), joinedload(Job.source))
            .where(Job.id == job_id)
            .limit(1)
        )
        if job is None:
            raise AppError("JOB_NOT_FOUND", "岗位不存在", status_code=404)
        return job

    def _cooldown_hours(self, options: dict[str, Any]) -> int:
        """How long a successfully verified posting stays out of the next sweep."""
        raw = options.get("cooldown_hours", DEFAULT_COOLDOWN_HOURS)
        if raw is None:
            return DEFAULT_COOLDOWN_HOURS
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_COOLDOWN_HOURS
        return max(0, min(value, MAX_COOLDOWN_HOURS))

    def _limit(self, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return MAX_JOBS_PER_RUN
        return max(1, min(parsed, MAX_JOBS_PER_RUN))

    def _closure_evidence(self, job: Job) -> dict[str, Any] | None:
        evidence = (job.archive_evidence_json or {}).get("last_closed_evidence")
        return evidence if isinstance(evidence, dict) else None

    def _item(self, job: Job) -> dict[str, Any]:
        evidence = self._closure_evidence(job) or {}
        return {
            "job_id": str(job.id),
            "company": job.company.name if job.company else None,
            "title": job.title,
            "city": job.city,
            "status": job.status,
            "archived": job.archived_at is not None,
            "last_checked_at": (job.last_checked_at.isoformat() if job.last_checked_at else None),
            "closed_checked_at": evidence.get("checked_at"),
            "closed_evidence": evidence.get("evidence"),
        }

    def _result(
        self,
        items: list[dict[str, Any]],
        counters: dict[str, int],
        unsupported: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {"items": items, "counters": counters, "unsupported": unsupported}
