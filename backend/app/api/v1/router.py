"""Versioned API router (`/api/v1`)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    agent,
    agent_runs,
    application_imports,
    applications,
    auth,
    dashboard,
    external_accounts,
    job_imports,
    job_leads,
    job_sources,
    job_syncs,
    jobs,
    mailboxes,
    matches,
    profile,
    resumes,
    saved_jobs,
    system,
)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(system.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(profile.router)
api_v1_router.include_router(resumes.router)
api_v1_router.include_router(jobs.router)
api_v1_router.include_router(saved_jobs.router)
api_v1_router.include_router(matches.router)
api_v1_router.include_router(agent.router)
api_v1_router.include_router(agent_runs.router)
api_v1_router.include_router(mailboxes.router)
api_v1_router.include_router(applications.router)
api_v1_router.include_router(application_imports.router)
api_v1_router.include_router(job_sources.router)
api_v1_router.include_router(job_syncs.router)
api_v1_router.include_router(job_imports.router)
api_v1_router.include_router(job_leads.router)
api_v1_router.include_router(external_accounts.router)
