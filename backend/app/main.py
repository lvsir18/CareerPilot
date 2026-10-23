"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.cache import close_redis
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.db.session import dispose_engine

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_startup",
            extra={
                "app_env": settings.app_env,
                "demo_mode": settings.demo_mode,
                "execution_mode": settings.execution_mode,
                "version": __version__,
            },
        )
        # Prepare the LangGraph checkpointer once at startup so per-request
        # setup never races on CONCURRENTLY index creation.
        try:
            from app.agents.checkpoint import checkpoint_saver

            with checkpoint_saver(settings):
                pass
        except Exception:  # agent stays available; checkpointer errors surface per-request
            logger.warning("agent_checkpoint_setup_failed", exc_info=True)
        yield
        dispose_engine()
        close_redis()
        logger.info("application_shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="CareerPilot 智能求职 Agent 后端 API",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    register_exception_handlers(app)
    if settings is not get_settings():
        app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


app = create_app()
