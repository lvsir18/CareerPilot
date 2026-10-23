"""Search provider contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import ClassVar, Protocol


class SearchError(Exception):
    code = "SEARCH_ERROR"

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class SearchNotConfigured(SearchError):
    code = "SEARCH_NOT_CONFIGURED"


class SearchRateLimited(SearchError):
    code = "SEARCH_RATE_LIMITED"


class SearchProviderError(SearchError):
    code = "SEARCH_PROVIDER_ERROR"


@dataclass(frozen=True, slots=True)
class SearchProviderInfo:
    name: str
    label: str
    role: str  # primary | fallback | deprecated | legacy
    configured: bool
    available: bool
    reason: str | None = None
    cost_note: str | None = None
    enabled: bool = True


@dataclass(slots=True)
class SearchHit:
    title: str
    url: str
    snippet: str | None = None
    company: str | None = None
    city: str | None = None
    job_type: str | None = None
    published_date: date | None = None
    rank: int = 0
    provider: str | None = None
    providers: list[str] = field(default_factory=list)
    url_type: str | None = None
    source_kind: str | None = None
    trusted_tenant: str | None = None
    search_layer: str | None = None


@dataclass(slots=True)
class CompanySearchDiagnostic:
    company: str
    queries: int = 0
    raw_results: int = 0
    detail_candidates: int = 0
    accepted: int = 0
    dropped_list_or_landing: int = 0
    dropped_unrelated: int = 0
    dropped_invalid: int = 0
    dropped_filter: int = 0
    provider_errors: int = 0
    layers: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass(slots=True)
class SearchOutcome:
    hits: list[SearchHit] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    configured: bool = False
    licensed_configured: bool = False
    warnings: list[str] = field(default_factory=list)
    cached: bool = False
    provider_queries: int = 0
    cached_queries: int = 0
    credits_estimated: int = 0
    diagnostics: list[CompanySearchDiagnostic] = field(default_factory=list)


class SearchProvider(Protocol):
    name: ClassVar[str]
    configured: bool

    def search(self, text: str, domains: list[str], limit: int) -> list[SearchHit]: ...
