"""Typed application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET = "replace_with_random_secret"
MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Runtime configuration.

    Every value can be overridden through environment variables (case-insensitive)
    or a local ``.env`` file. Secrets never get a production-safe default: the
    validator below refuses to boot production with the sample secret.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "CareerPilot API"
    app_env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    database_url: str = "postgresql+psycopg://career:career_dev_only@localhost:5432/careerpilot"
    redis_url: str = "redis://localhost:6379/0"

    session_secret: str = PLACEHOLDER_SECRET
    session_cookie_name: str = "careerpilot_session"
    auth_session_ttl_days: int = Field(default=7, ge=1, le=30)
    # Argon2 is one-way, so a forgotten password cannot be recovered. Local
    # single-user deployments may opt into a direct email reset; production
    # keeps it off by default.
    password_reset_enabled: bool = False

    # Cookie / CSRF hardening. ``cookie_secure=None`` means "true only in production".
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    csrf_cookie_name: str = "careerpilot_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    csrf_trusted_origins: list[str] = Field(default_factory=list)
    # Allow http(s) origins whose host is a private IP (LAN / Tailscale). A phone
    # opening http://192.168.1.10:3000 otherwise fails the origin check, and the
    # address changes with every network. Public domains must still be listed.
    allow_lan_origins: bool = False

    # Login/register rate limiting (Redis). Fail-open with a warning when Redis
    # is unavailable so a cache outage cannot take down authentication.
    login_rate_limit_enabled: bool = True
    login_rate_limit_ip_attempts: int = Field(default=20, ge=1, le=1000)
    login_rate_limit_ip_window_seconds: int = Field(default=300, ge=10, le=86400)
    login_rate_limit_account_attempts: int = Field(default=5, ge=1, le=1000)
    login_rate_limit_account_window_seconds: int = Field(default=300, ge=10, le=86400)
    trust_proxy_headers: bool = False

    # Users allowed to trigger data-source syncs (comma separated). Empty = nobody.
    admin_emails: str = ""

    # External account connections are disabled unless the provider is explicitly
    # reviewed/allow-listed. Browser-session automation has a separate switch.
    external_auth_allowed_providers: list[str] = Field(default_factory=list)
    external_auth_allow_browser_session: bool = False

    # M2-R3 discovery: Tavily is the only licensed search API.
    # ``search_provider=none`` keeps the app usable with database jobs, the
    # Baidu official list page and manual imports. The key is env-only.
    search_provider: Literal["none", "tavily"] = "none"
    tavily_api_key: str | None = None
    # A shared key is the deployment owner's quota. Keep it to admins by default
    # so other accounts on the LAN configure their own instead.
    shared_llm_key_admins_only: bool = True
    shared_search_key_admins_only: bool = True
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_max_results: int = Field(default=10, ge=1, le=20)
    tavily_max_queries_per_request: int = Field(default=20, ge=1, le=20)
    search_max_queries_per_request: int = Field(default=20, ge=1, le=20)
    search_max_concurrent_requests: int = Field(default=1, ge=1, le=5)
    tavily_max_query_terms: int = Field(default=3, ge=1, le=5)
    tavily_extract_depth: Literal["basic", "advanced"] = "basic"
    tavily_extract_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    tavily_extract_daily_budget: int = Field(default=30, ge=1, le=1000)
    tavily_extract_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400)
    search_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    search_max_results: int = Field(default=10, ge=1, le=50)
    search_rate_limit_per_minute: int = Field(default=30, ge=1, le=300)
    search_daily_budget_per_provider: int = Field(default=50, ge=1, le=10000)
    search_cache_ttl_seconds: int = Field(default=600, ge=0, le=86400)
    official_site_discovery_enabled: bool = True
    lead_verify_rate_limit_per_minute: int = Field(default=10, ge=1, le=100)

    file_storage_dir: Path = Path("./var/uploads")
    max_resume_mb: int = Field(default=10, ge=1, le=50)

    llm_provider: str = "openai_compatible"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_temperature: float = Field(default=0.0, ge=0, le=2)

    # M4 LangGraph agent runtime limits.
    agent_max_tool_calls: int = Field(default=12, ge=1, le=100)
    agent_max_graph_steps: int = Field(default=30, ge=1, le=200)
    agent_max_runtime_seconds: int = Field(default=90, ge=1, le=600)
    agent_max_search_calls: int = Field(default=3, ge=1, le=20)
    agent_checkpoint_ttl_hours: int = Field(default=24 * 30, ge=1, le=24 * 365)

    # M5.1 mailbox connections. Credentials are encrypted with Fernet; the key
    # must come from the environment and never be committed.
    mailbox_secret_key: str | None = None
    mailbox_sync_enabled: bool = True
    mailbox_sync_interval_minutes: int = Field(default=15, ge=5, le=1440)
    mailbox_sync_lookback_days: int = Field(default=30, ge=1, le=365)
    mailbox_sync_max_messages: int = Field(default=200, ge=1, le=2000)
    qq_imap_host: str = "imap.qq.com"
    qq_imap_port: int = Field(default=993, ge=1, le=65535)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None

    enable_public_connectors: bool = False
    job_sync_enabled: bool = False
    job_sync_interval_minutes: int = Field(default=60, ge=5, le=1440)

    # Connector HTTP policy (all values environment-overridable).
    connector_user_agent: str = "CareerPilotBot/0.1 (+https://careerpilot.local/bot)"
    connector_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    connector_max_retries: int = Field(default=2, ge=0, le=5)
    connector_backoff_seconds: float = Field(default=1.0, ge=0, le=30)
    connector_min_interval_seconds: float = Field(default=1.0, ge=0, le=30)
    connector_max_pages: int = Field(default=20, ge=1, le=100)
    connector_page_size: int = Field(default=50, ge=1, le=100)
    connector_max_response_bytes: int = Field(default=5_000_000, ge=100_000)

    # Official Alibaba TOP API (alibaba.recruit.position.pagesearch). Disabled
    # until all values are provided by the deployment owner.
    alibaba_app_key: str | None = None
    alibaba_app_secret: str | None = None
    alibaba_tenant_id: str | None = None
    alibaba_position_url_template: str | None = None

    manual_import_dir: Path = Path("./fixtures/manual")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = Field(default_factory=list)

    db_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)
    redis_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def llm_configured(self) -> bool:
        """True only when a model name, key and base URL are all provided."""
        return bool(self.llm_api_key and self.llm_model and self.llm_base_url)

    @property
    def execution_mode(self) -> Literal["llm", "rule_fallback"]:
        """Which reasoning mode the agent layer will be able to use."""
        return "llm" if self.llm_configured else "rule_fallback"

    @property
    def effective_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production

    @property
    def effective_cookie_domain(self) -> str | None:
        return self.cookie_domain or None

    @property
    def effective_csrf_origins(self) -> list[str]:
        """Trusted origins for state-changing requests (never the CORS list)."""
        configured = self.csrf_trusted_origins or [self.frontend_base_url, self.api_base_url]
        return [origin.rstrip("/").lower() for origin in configured if origin]

    @property
    def admin_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails.split(",") if email.strip()}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_origins(self) -> list[str]:
        """CORS allow-list; explicit CORS_ORIGINS wins over the frontend URL."""
        if self.cors_origins:
            return self.cors_origins
        return [self.frontend_base_url]

    @model_validator(mode="after")
    def _validate_production_safety(self) -> Settings:
        if not self.is_production:
            return self

        if (
            self.session_secret == PLACEHOLDER_SECRET
            or len(self.session_secret) < MIN_PRODUCTION_SECRET_LENGTH
        ):
            raise ValueError(
                "SESSION_SECRET must be replaced with a random value of at least "
                f"{MIN_PRODUCTION_SECRET_LENGTH} characters when APP_ENV=production"
            )
        if self.demo_mode:
            raise ValueError("DEMO_MODE must be false when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton (also used as a FastAPI dependency)."""
    return Settings()
