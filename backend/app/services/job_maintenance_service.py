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
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.connectors.rendered_page import RenderedPageReader
from app.connectors.schemas import RawJob
from app.connectors.tencent_campus import TencentCampusConnector
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.enums import JobStatus, VerificationStatus
from app.db.models.job import Job
from app.db.models.job_maintenance import JobMaintenanceRun
from app.db.models.user import User
from app.repositories.jobs import JobQuery, JobRepository
from app.search.domains import resolve_company
from app.services.job_ingestion import compute_content_hash
from app.services.official_jobs_service import OfficialJobsService

logger = get_logger(__name__)

ACTIVE_STATUSES = ("queued", "running")
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
        if kind not in {"refresh", "discover", "prune"}:
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
        run = self.get_run(run_id)
        if run.status in ACTIVE_STATUSES:
            run.cancel_requested_at = datetime.now(UTC)
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
                datetime.now(UTC) - timedelta(hours=cooldown_hours)
                if cooldown_hours > 0
                else None
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
            discovered = self._discover(scope, options, unsupported)
            for item in discovered:
                items.append(item)
                counters[item["outcome"]] = counters.get(item["outcome"], 0) + 1
            counters[OUTCOME_UNSUPPORTED] += len(unsupported)
            total += len(discovered)
            self.set_progress(
                run_id, total=total, processed=total, counters=counters, current="发现新增岗位"
            )

        failed = len([item for item in items if item["outcome"] == OUTCOME_UNCONFIRMED])
        status = "success" if failed == 0 else "partial"
        self.finish(run_id, status=status, result=self._result(items, counters, unsupported))
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
            title=(snapshot.get("title") or job.title)[:300],
            source_url=job.source_url,
            description=snapshot.get("description"),
            department=job.department,
            recruitment_program=job.recruitment_program,
            location_text=snapshot.get("location_text") or job.location_text,
            city=snapshot.get("city") or job.city,
            job_type=snapshot.get("job_type") or job.job_type,
            requirements=job.requirements_json or [],
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
    def _discover(
        self,
        scope: dict[str, Any],
        options: dict[str, Any],
        unsupported: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        catalogue = OfficialJobsService(self._session, self._settings).supported()
        supported_keys = [item["key"] for item in catalogue if item.get("supported")]
        labels = {item["key"]: item["label"] for item in catalogue}

        requested = [resolve_company(str(name)) for name in scope.get("companies") or []]
        keys = [key for key in requested if key]
        if not keys:
            keys = supported_keys[:MAX_DISCOVER_COMPANIES]
        keys = [key for key in dict.fromkeys(keys) if key in supported_keys][
            : max(1, min(int(options.get("max_companies", MAX_DISCOVER_COMPANIES)), 10))
        ]
        for value in scope.get("companies") or []:
            if resolve_company(str(value)) is None:
                unsupported.append({"name": str(value), "reason": "暂不支持自动发现"})

        keyword = (scope.get("q") or "").strip() or None
        service = OfficialJobsService(self._session, self._settings)
        try:
            result = service.search(
                companies=keys,
                keyword=keyword,
                limit=MAX_DISCOVER_PER_COMPANY,
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
