"""Business tools exposed to agents.

Tools are built per-user with a trusted RuntimeContext. ``user_id`` is closed
over from the authenticated context and never accepted from LLM arguments.
All tools return trimmed, JSON-serializable data (no full resume/email bodies).
"""

from __future__ import annotations

import functools
import inspect
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.runtime import RunCancelled, RuntimeContext
from app.core.errors import AppError
from app.db.models.application import Application
from app.db.models.job import Job
from app.schemas.applications import application_staleness
from app.services.application_service import ApplicationService
from app.services.job_discovery_service import JobDiscoveryService
from app.services.job_lead_service import JobLeadService
from app.services.job_service import JobService
from app.services.official_jobs_service import OfficialJobsService
from app.services.profile_service import ProfileService
from app.services.recommendation_service import RecommendationService
from app.services.tencent_campus_service import TencentCampusService


class SearchJobsInput(BaseModel):
    keywords: list[str] = Field(default_factory=list, description="岗位关键词，如 [大模型, 算法]")
    companies: list[str] = Field(
        default_factory=list, description="企业 key，如 [bytedance, minimax]"
    )
    cities: list[str] = Field(default_factory=list, description="城市，如 [北京, 上海]")
    job_types: list[str] = Field(default_factory=list, description="internship / campus")
    limit: int = Field(default=10, ge=1, le=30)


class ImportOfficialJobsInput(BaseModel):
    companies: list[str] = Field(
        default_factory=lambda: ["tencent"],
        description=(
            "企业英文键，可选：tencent(腾讯) / bytedance(字节跳动) / "
            "xiaohongshu(小红书) / bilibili(哔哩哔哩) / meituan(美团)"
        ),
    )
    keyword: str | None = Field(
        default=None, description="岗位关键词，如 算法、大模型、推荐；留空表示不限定"
    )
    project: str = Field(
        default="日常实习",
        description="仅腾讯生效：日常实习 / 应届实习 / 应届毕业生 / 青云计划-*",
    )
    limit: int = Field(default=5, ge=1, le=10, description="每家公司最多返回条数")


class RecommendJobsInput(BaseModel):
    companies: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    job_types: list[str] = Field(default_factory=list)
    exclude_applied: bool = Field(default=False)
    limit: int = Field(default=10, ge=1, le=30)


def _lead_brief(lead: Any) -> dict[str, Any]:
    company = getattr(lead.company, "name", lead.company)
    status = lead.verification_status
    status_value = status.value if hasattr(status, "value") else str(status)
    last_seen = getattr(lead, "last_seen_at", None)
    published = getattr(lead, "published_date", None)
    return {
        "id": str(lead.id),
        "company": company,
        "title": lead.title,
        "summary": (lead.summary or "")[:300],
        "official_url": lead.official_url,
        "verification_status": status_value,
        "published_date": published.isoformat() if published else None,
        "last_seen_at": last_seen.isoformat() if last_seen else None,
    }


_BEIJING = ZoneInfo("Asia/Shanghai")


def _local_label(value: datetime | None) -> str | None:
    """Render an instant in the user's timezone so the model never converts.

    The agent used to echo the raw UTC wall clock and call it "北京时间", which
    is exactly the kind of arithmetic a tool should do instead of a model.
    """
    if value is None:
        return None
    return value.astimezone(_BEIJING).strftime("%Y-%m-%d %H:%M") + "（北京时间）"


def _local_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(_BEIJING).isoformat()


def build_job_tools(ctx: RuntimeContext) -> list:
    @tool("search_jobs", args_schema=SearchJobsInput)
    @_safe_tool(ctx)
    def search_jobs(
        keywords: list[str],
        companies: list[str],
        cities: list[str],
        job_types: list[str],
        limit: int,
    ) -> dict[str, Any]:
        """搜索互联网招聘岗位，返回已核验岗位与搜索候选（分开标注）。"""
        outcome = JobDiscoveryService(ctx.session, ctx.settings).discover(
            ctx.user_id,
            query=" ".join(keywords),
            companies=companies,
            city=(cities[0] if len(cities) == 1 else None),
            job_type=(job_types[0] if len(job_types) == 1 else None),
            page=1,
            page_size=min(limit, 30),
        )
        # Leads come from the shared database pool, so a repeat query (or an
        # exhausted search budget) still returns rows without new evidence.
        fresh_queries = outcome.search.tavily_queries - outcome.search.tavily_cached_queries
        notice = "history_only" if outcome.leads and fresh_queries <= 0 else None
        return {
            "jobs": [
                {
                    "id": str(job.id),
                    "company": job.company,
                    "title": job.title,
                    "city": job.city,
                    "job_type": job.job_type,
                    "source_url": job.source_url,
                    "verification_status": job.verification_status,
                }
                for job in outcome.jobs
            ],
            "leads": [_lead_brief(lead) for lead in outcome.leads],
            "leads_notice": notice,
            "warnings": outcome.search.warnings,
        }

    @tool("get_job_detail")
    @_safe_tool(ctx)
    def get_job_detail(job_id: str) -> dict[str, Any]:
        """读取已核验岗位的完整 JD 详情。"""
        job = JobService(ctx.session, ctx.settings).get_job(UUID(job_id))
        return {
            "id": str(job.id),
            "company": job.company.name,
            "title": job.title,
            "city": job.city,
            "job_type": job.job_type,
            "department": job.department,
            "description": (job.description or "")[:2000],
            "requirements": list(job.requirements_json or [])[:30],
            "source_url": job.source_url,
            "verification_status": job.verification_status.value,
        }

    @tool("get_job_leads")
    @_safe_tool(ctx)
    def get_job_leads(company: str | None = None, limit: int = 10) -> dict[str, Any]:
        """列出搜索候选 JobLead（只有摘要，不含完整 JD）。"""
        leads = JobLeadService(ctx.session, ctx.settings).list_for_user(
            ctx.user_id, company=company, limit=min(limit, 30)
        )
        return {
            "leads": [_lead_brief(lead) for lead in leads],
            "leads_notice": "library_only" if leads else None,
        }

    @tool("import_official_jobs", args_schema=ImportOfficialJobsInput)
    @_safe_tool(ctx)
    def import_official_jobs(
        companies: list[str],
        keyword: str | None,
        project: str,
        limit: int,
    ) -> dict[str, Any]:
        """直连企业官方招聘页检索岗位，含完整 JD、城市、招聘类型与官方网址。

        这些站点是前端渲染（腾讯除外），search_jobs 抓 HTML 只能拿到空白页，
        因此用户要「某公司的具体岗位/网址/JD」时必须先用本工具，
        不要用 search_jobs 的链接去猜。
        """
        if companies == ["tencent"] and project:
            result = TencentCampusService(ctx.session, ctx.settings).import_jobs(
                keyword=keyword,
                project=project,
                limit=limit,
            )
            return {
                "company": result["company"],
                "project": result["project"],
                "matched": result["matched"],
                "created": result["created"],
                "updated": result["updated"],
                "jobs": result["jobs"],
                "failures": result["failures"],
            }
        result = OfficialJobsService(ctx.session, ctx.settings).search(
            companies=companies,
            keyword=keyword,
            limit=limit,
            project=project,
        )
        return {
            "keyword": result["keyword"],
            "created": result["created"],
            "updated": result["updated"],
            "companies": result["companies"],
            "jobs": result["jobs"],
        }

    return [search_jobs, get_job_detail, get_job_leads, import_official_jobs]


def build_match_tools(ctx: RuntimeContext) -> list:
    service = RecommendationService(ctx.session, ctx.settings)

    @tool("recommend_jobs", args_schema=RecommendJobsInput)
    @_safe_tool(ctx)
    def recommend_jobs(
        companies: list[str],
        cities: list[str],
        job_types: list[str],
        exclude_applied: bool,
        limit: int,
    ) -> dict[str, Any]:
        """基于已确认画像执行岗位匹配，返回可解释得分与技能证据。"""
        items, _total = service.recommendations(
            ctx.user,
            companies=tuple(companies),
            cities=tuple(cities),
            job_types=tuple(job_types),
            exclude_applied=exclude_applied,
            page=1,
            page_size=min(limit, 30),
        )
        return {
            "items": [
                {
                    "job": {
                        "id": str(item.job.id),
                        "company": item.job.company,
                        "title": item.job.title,
                        "city": item.job.city,
                        "job_type": item.job.job_type,
                        "source_url": item.job.source_url,
                    },
                    "match": item.match.model_dump(),
                    "applied_status": item.applied_status,
                }
                for item in items
            ]
        }

    @tool("match_job")
    @_safe_tool(ctx)
    def match_job(job_id: str) -> dict[str, Any]:
        """对单个已核验岗位执行完整匹配并返回解释。"""
        item = service.match_job(ctx.user, UUID(job_id))
        return {
            "job": {
                "id": str(item.job.id),
                "company": item.job.company,
                "title": item.job.title,
                "city": item.job.city,
                "job_type": item.job.job_type,
                "source_url": item.job.source_url,
            },
            "match": item.match.model_dump(),
            "applied_status": item.applied_status,
        }

    return [recommend_jobs, match_job]


def build_profile_tools(ctx: RuntimeContext) -> list:
    @tool("get_profile_summary")
    @_safe_tool(ctx)
    def get_profile_summary() -> dict[str, Any]:
        """读取已确认用户画像和求职偏好（只读）。"""
        read = ProfileService(ctx.session).get(ctx.user)
        return {
            "headline": read.headline,
            "skills": read.skills,
            "education": [
                {
                    "school": e.school,
                    "degree": e.degree,
                    "major": e.major,
                    "graduation_year": e.graduation_year,
                }
                for e in read.education
            ],
            "preferences": {
                "target_roles": read.preferences.target_roles,
                "cities": read.preferences.cities,
                "job_types": read.preferences.job_types,
                "target_companies": read.preferences.target_companies,
                "graduation_year": read.preferences.graduation_year,
                "remote_ok": read.preferences.remote_ok,
            },
            "version": read.version,
            "confirmed": read.verified_by_user,
        }

    return [get_profile_summary]


def build_progress_tools(ctx: RuntimeContext) -> list:
    service = ApplicationService(ctx.session, ctx.settings)

    def _next_appointment(app: Application) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        upcoming = [
            event
            for event in app.events
            if getattr(event, "is_scheduled", False)
            and getattr(event, "superseded_at", None) is None
            and event.event_time is not None
            and event.event_time >= now
        ]
        if not upcoming:
            return None
        soonest = min(upcoming, key=lambda event: event.event_time)
        return {
            "status": soonest.to_status.value,
            "starts_at": _local_iso(soonest.event_time),
            # Pre-rendered: the model used to echo the UTC wall clock and call it
            # "北京时间", so the conversion happens here instead of in the prompt.
            "starts_at_label": _local_label(soonest.event_time),
        }

    @tool("list_applications")
    @_safe_tool(ctx)
    def list_applications(company: str | None = None) -> dict[str, Any]:
        """查询用户已登记申请记录（可按公司过滤）。"""
        applications, _total = service.list(
            ctx.user, status=None, company=company, query=None, page=1, page_size=50
        )
        rows: list[dict[str, Any]] = []
        for app in applications:
            # ``needs_review`` is derived by the API serializer, not an ORM column:
            # reading it off the model raises AttributeError and kills the tool.
            needs_review, stale_days = application_staleness(app)
            rows.append(
                {
                    "id": str(app.id),
                    # Every identifier a follow-up tool may need, so the model
                    # never has to guess which id an API expects.
                    "application_id": str(app.id),
                    "job_id": str(app.job.id) if app.job is not None else None,
                    "job_no": app.job.source_job_id if app.job is not None else None,
                    "company": (app.job.company.name if app.job else app.external_company),
                    "title": (app.job.title if app.job else app.external_title),
                    "status": app.status.value,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else None,
                    "last_confirmed_at": (
                        app.last_confirmed_at.isoformat() if app.last_confirmed_at else None
                    ),
                    "next_appointment": _next_appointment(app),
                    "needs_review": needs_review,
                    "stale_days": stale_days,
                }
            )
        return {"total": len(rows), "applications": rows, "timezone": "Asia/Shanghai"}

    @tool("get_application_timeline")
    @_safe_tool(ctx)
    def get_application_timeline(application_id: str) -> dict[str, Any]:
        """读取某条申请的状态时间线与事件证据。"""
        try:
            app_uuid = UUID(application_id)
        except (TypeError, ValueError):
            return {
                "error": "INVALID_APPLICATION_ID",
                "message": "需要申请 id（UUID）。可先用 list_applications 查询 application_id。",
            }
        events = service.events(ctx.user, app_uuid)
        rows: list[dict[str, Any]] = []
        for event in events:
            scheduled = bool(getattr(event, "is_scheduled", False))
            superseded_at = getattr(event, "superseded_at", None)
            active = scheduled and superseded_at is None
            rows.append(
                {
                    # ``ApplicationEvent`` exposes ``to_status``; ``new_status``
                    # never existed and made the timeline tool always fail.
                    "status": event.to_status.value,
                    "appointment": active,
                    "is_scheduled": scheduled,
                    "appointment_state": "active" if active else "inactive" if scheduled else None,
                    "superseded_at": _local_iso(superseded_at),
                    # Appointment slot vs. the moment it was recorded: only the
                    # former is a calendar item, and both are pre-localised.
                    "starts_at": _local_iso(event.event_time) if scheduled else None,
                    "starts_at_label": _local_label(event.event_time) if scheduled else None,
                    "recorded_at": _local_label(event.created_at),
                    "event_time": event.event_time.isoformat() if event.event_time else None,
                    "source_type": event.source_type,
                    "evidence_type": event.evidence_type,
                    "summary": (event.evidence_summary or "")[:300],
                }
            )
        return {
            "application_id": str(app_uuid),
            "events": rows,
            "timezone": "Asia/Shanghai",
        }

    @tool("check_job_application_status")
    @_safe_tool(ctx)
    def check_job_application_status(identifier: str) -> dict[str, Any]:
        """查询某个岗位是否已申请及当前状态。

        identifier 支持三种值：本账号申请 id、内部岗位 UUID、来源编号
        （source_job_id，通常是官网详情链接里的数字串或 UUID）。
        标题里的展示编号（如「（J106720）」）不一定等于来源编号，若查不到会返回
        IDENTIFIER_NOT_RECOGNIZED，此时应先 list_applications 取真实 id，不要把
        查不到说成「未申请」。
        """
        target = (identifier or "").strip()
        if not target:
            return {
                "error": "IDENTIFIER_REQUIRED",
                "message": "需要申请 id、岗位 UUID 或官网岗位编号",
            }
        applications, _total = service.list(
            ctx.user, status=None, company=None, query=None, page=1, page_size=200
        )
        for app in applications:
            candidates = {str(app.id)}
            if app.job is not None:
                candidates.add(str(app.job.id))
                if app.job.source_job_id:
                    candidates.add(app.job.source_job_id.strip())
            if target in candidates:
                return {
                    "applied": True,
                    "status": app.status.value,
                    "application_id": str(app.id),
                    "job_id": str(app.job.id) if app.job is not None else None,
                    "job_no": app.job.source_job_id if app.job is not None else None,
                }
        job = _find_job(ctx, target)
        if job is not None:
            return {
                "applied": False,
                "status": None,
                "job_id": str(job.id),
                "job_no": job.source_job_id,
                "company": job.company,
                "title": job.title,
                "message": "该岗位在你的记录中还没有申请",
            }
        return {
            "error": "IDENTIFIER_NOT_RECOGNIZED",
            "message": (
                "无法识别该编号：请使用 list_applications 返回的 application_id、"
                "job_id 或 job_no，不要用其它数字推断申请状态。"
            ),
        }

    return [list_applications, get_application_timeline, check_job_application_status]


def _find_job(ctx: RuntimeContext, identifier: str) -> Job | None:
    """Resolve a job by internal UUID or by its official posting number."""
    statement = select(Job)
    try:
        job_id = UUID(identifier)
    except (TypeError, ValueError):
        statement = statement.where(Job.source_job_id == identifier)
    else:
        statement = statement.where(Job.id == job_id)
    return ctx.session.execute(statement.limit(1)).scalar_one_or_none()


def _safe_tool(ctx: RuntimeContext):
    """Turn business errors into structured tool output.

    LangChain lets a tool exception abort the whole agent run; the model can
    recover only if it sees a structured error instead. Every result (success
    or error) is also recorded on the runtime context so the run's structured
    payload never depends on how ToolMessage content gets serialised.
    """

    def decorate(fn):
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Both the pre-tool cancel query and the tool use ctx.session.
            # Serialize the whole operation, not just the business query.
            with ctx.tool_lock:
                # ToolNode turns exceptions into tool messages, so cancellation
                # returns a marker; the graph stops at its next node boundary.
                if ctx.cancel_check is not None and ctx.cancel_check():
                    result = {"error": "RUN_CANCELLED", "message": "用户已取消该任务"}
                    ctx.record_tool(fn.__name__, result)
                    return result
                try:
                    result = fn(*args, **kwargs)
                except RunCancelled:
                    raise
                except AppError as exc:
                    result = {"error": exc.code, "message": exc.message}
                except Exception as exc:
                    result = {"error": "TOOL_FAILED", "message": str(exc)[:300]}
                ctx.record_tool(fn.__name__, result)
                return result

        wrapper.__signature__ = signature
        return wrapper

    return decorate


def build_all_tools(ctx: RuntimeContext) -> list:
    return [
        *build_job_tools(ctx),
        *build_match_tools(ctx),
        *build_profile_tools(ctx),
        *build_progress_tools(ctx),
    ]
