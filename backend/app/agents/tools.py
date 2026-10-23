"""Business tools exposed to agents.

Tools are built per-user with a trusted RuntimeContext. ``user_id`` is closed
over from the authenticated context and never accepted from LLM arguments.
All tools return trimmed, JSON-serializable data (no full resume/email bodies).
"""

from __future__ import annotations

import functools
import inspect
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.runtime import RuntimeContext
from app.core.errors import AppError
from app.services.application_service import ApplicationService
from app.services.job_discovery_service import JobDiscoveryService
from app.services.job_lead_service import JobLeadService
from app.services.job_service import JobService
from app.services.profile_service import ProfileService
from app.services.recommendation_service import RecommendationService


class SearchJobsInput(BaseModel):
    keywords: list[str] = Field(default_factory=list, description="岗位关键词，如 [大模型, 算法]")
    companies: list[str] = Field(
        default_factory=list, description="企业 key，如 [bytedance, minimax]"
    )
    cities: list[str] = Field(default_factory=list, description="城市，如 [北京, 上海]")
    job_types: list[str] = Field(default_factory=list, description="internship / campus")
    limit: int = Field(default=10, ge=1, le=30)


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
    return {
        "id": str(lead.id),
        "company": company,
        "title": lead.title,
        "summary": (lead.summary or "")[:300],
        "official_url": lead.official_url,
        "verification_status": status_value,
    }


def build_job_tools(ctx: RuntimeContext) -> list:
    @tool("search_jobs", args_schema=SearchJobsInput)
    @_safe_tool
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
            "warnings": outcome.search.warnings,
        }

    @tool("get_job_detail")
    @_safe_tool
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
    @_safe_tool
    def get_job_leads(company: str | None = None, limit: int = 10) -> dict[str, Any]:
        """列出搜索候选 JobLead（只有摘要，不含完整 JD）。"""
        leads = JobLeadService(ctx.session, ctx.settings).list_for_user(
            ctx.user_id, company=company, limit=min(limit, 30)
        )
        return {"leads": [_lead_brief(lead) for lead in leads]}

    return [search_jobs, get_job_detail, get_job_leads]


def build_match_tools(ctx: RuntimeContext) -> list:
    service = RecommendationService(ctx.session, ctx.settings)

    @tool("recommend_jobs", args_schema=RecommendJobsInput)
    @_safe_tool
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
    @_safe_tool
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
    @_safe_tool
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

    @tool("list_applications")
    @_safe_tool
    def list_applications(company: str | None = None) -> dict[str, Any]:
        """查询用户已登记申请记录（可按公司过滤）。"""
        applications, _total = service.list(
            ctx.user, status=None, company=company, query=None, page=1, page_size=50
        )
        return {
            "applications": [
                {
                    "id": str(app.id),
                    "company": (app.job.company.name if app.job else app.external_company),
                    "title": (app.job.title if app.job else app.external_title),
                    "status": app.status.value,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else None,
                    "last_confirmed_at": app.last_confirmed_at.isoformat()
                    if app.last_confirmed_at
                    else None,
                    "needs_review": app.needs_review,
                }
                for app in applications
            ]
        }

    @tool("get_application_timeline")
    @_safe_tool
    def get_application_timeline(application_id: str) -> dict[str, Any]:
        """读取某条申请的状态时间线与事件证据。"""
        events = service.events(ctx.user, UUID(application_id))
        return {
            "events": [
                {
                    "status": event.new_status,
                    "event_time": event.event_time.isoformat() if event.event_time else None,
                    "source_type": event.source_type,
                    "evidence_type": event.evidence_type,
                    "summary": (event.evidence_summary or "")[:300],
                }
                for event in events
            ]
        }

    @tool("check_job_application_status")
    @_safe_tool
    def check_job_application_status(job_id: str) -> dict[str, Any]:
        """查询某个岗位是否已申请及当前状态。"""
        applications, _total = service.list(
            ctx.user, status=None, company=None, query=None, page=1, page_size=200
        )
        for app in applications:
            if app.job is not None and str(app.job.id) == job_id:
                return {"applied": True, "status": app.status.value, "application_id": str(app.id)}
        return {"applied": False, "status": None}

    return [list_applications, get_application_timeline, check_job_application_status]


def _safe_tool(fn):
    """Turn business errors into structured tool output.

    LangChain lets a tool exception abort the whole agent run; the model can
    recover only if it sees a structured error instead.
    """
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AppError as exc:
            return {"error": exc.code, "message": exc.message}
        except Exception as exc:
            return {"error": "TOOL_FAILED", "message": str(exc)[:300]}

    wrapper.__signature__ = signature
    return wrapper


def build_all_tools(ctx: RuntimeContext) -> list:
    return [
        *build_job_tools(ctx),
        *build_match_tools(ctx),
        *build_profile_tools(ctx),
        *build_progress_tools(ctx),
    ]
