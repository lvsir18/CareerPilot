/**
 * Typed server-side client for the CareerPilot API.
 *
 * Failures are returned as values (never thrown) so pages can render honest
 * degraded states. Requests that need a session receive the caller's Cookie
 * header explicitly from a server component.
 */

import { buildJobQuery, type JobFilters } from "@/lib/job-filters";

const DEFAULT_TIMEOUT_MS = 3000;

export function getApiBaseUrl(): string {
  const baseUrl =
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000";
  return baseUrl.replace(/\/+$/, "");
}

export interface ApiErrorInfo {
  code: string;
  message: string;
  status?: number;
  details?: Record<string, unknown>;
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiErrorInfo };

export interface SystemInfo {
  app_name: string;
  version: string;
  app_env: string;
  demo_mode: boolean;
  execution_mode: "llm" | "rule_fallback";
  llm_configured: boolean;
  public_connectors_enabled: boolean;
  job_sync_enabled: boolean;
  api_docs_url: string;
}

export interface DependencyCheck {
  name: string;
  status: "ok" | "error";
  detail: string | null;
}

export interface ReadinessSnapshot {
  reachable: boolean;
  ready: boolean;
  checks: DependencyCheck[];
  checkedAt: string | null;
  error: ApiErrorInfo | null;
}

export interface SessionUser {
  id: string;
  email: string;
  created_at: string;
  /** Only /auth/me fills this; used to show library-wide archive actions. */
  is_admin?: boolean;
}

export interface MaintenanceScope {
  q?: string | null;
  companies: string[];
  cities: string[];
  job_types: string[];
  source_types: string[];
  recruitment_programs: string[];
}

export interface MaintenanceItem {
  job_id: string | null;
  company: string | null;
  title: string | null;
  city: string | null;
  status?: string | null;
  archived?: boolean;
  outcome: string;
  reason?: string | null;
  closed_checked_at?: string | null;
  closed_evidence?: string | null;
}

export interface MaintenanceRun {
  id: string;
  kind: "refresh" | "discover" | "prune";
  status: string;
  progress: {
    total?: number;
    processed?: number;
    current?: string;
    counters?: Record<string, number>;
  };
  result: {
    items?: MaintenanceItem[];
    counters?: Record<string, number>;
    unsupported?: { name: string; reason: string }[];
  };
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface PrunePreview {
  count: number;
  items: MaintenanceItem[];
  truncated: boolean;
}

/** Non-terminal background work owned by the current user. */
export interface ActivitySnapshot {
  job_maintenance: {
    run_id: string;
    kind: string;
    status: string;
    total: number;
    processed: number;
  } | null;
  agent: { run_id: string; thread_id: string; status: string } | null;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
}

export interface Page<T> {
  data: T[];
  meta: PageMeta;
}

export interface JobListItem {
  id: string;
  company: string;
  title: string;
  department: string | null;
  city: string | null;
  location_text: string | null;
  job_type: string | null;
  recruitment_program: string | null;
  source_type: string;
  source_key: string;
  source_url: string;
  published_at: string | null;
  first_seen_at: string;
  status: string;
  is_demo: boolean;
  source_method: string;
  verification_status: string;
  verified_at: string | null;
  job_family: string;
}

export interface SourceEvidence {
  id: string;
  source_url: string;
  evidence_kind: string;
  captured_at: string;
  verification_method: string;
  evidence_ref: string | null;
  content_hash: string | null;
}

export interface JobDetail extends JobListItem {
  description: string | null;
  requirements: string[];
  skills: string[];
  official_job_id: string | null;
  last_checked_at: string | null;
  evidence: SourceEvidence[];
}

export interface JobLead {
  id: string;
  company: string;
  title: string;
  official_url: string;
  summary: string | null;
  source_method: string;
  verification_status: "search_snippet_only" | "user_provided" | "verified_official" | "stale";
  published_date: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_verified_at: string | null;
  last_verification_error: string | null;
  last_verification_attempt_at: string | null;
  job_id: string | null;
  is_private: boolean;
  job_family: string;
  source_kind: string;
  url_type: string;
}

export interface JobLeadDetail {
  lead: JobLead;
  evidence: SourceEvidence[];
}

export interface SearchProviderResult {
  title: string;
  url: string;
  snippet: string | null;
  company: string;
  published_date: string | null;
  providers: string[];
  rank: number;
  url_type: string;
  source_kind: string;
  trusted_tenant: string | null;
}

export interface CompanySearchDiagnostic {
  company: string;
  queries: number;
  raw_results: number;
  detail_candidates: number;
  accepted: number;
  dropped_list_or_landing: number;
  dropped_unrelated: number;
  dropped_invalid: number;
  dropped_filter: number;
  provider_errors: number;
  layers: string[];
  reason: string | null;
}

export interface SearchProviderStatus {
  name: string;
  label: string;
  role: string;
  configured: boolean;
  available: boolean;
  enabled: boolean;
  reason: string | null;
  cost_note: string | null;
}

export interface DiscoveryResponse {
  query: string | null;
  companies: string[];
  job_family: string | null;
  sort: string;
  verification: string;
  published_within_days: number | null;
  page: number;
  page_size: number;
  total_pages: number;
  jobs: JobListItem[];
  leads: JobLead[];
  search: {
    configured: boolean;
    licensed_configured: boolean;
    providers_used: string[];
    provider_results: SearchProviderResult[];
    provider_statuses: SearchProviderStatus[];
    warnings: string[];
    discovery_window_days: number | null;
    searched_at: string;
    tavily_queries: number;
    tavily_cached_queries: number;
    credits_estimated: number;
    diagnostics: CompanySearchDiagnostic[];
  };
  total_jobs: number;
  total_leads: number;
}

export interface JobImportPreview {
  source_url: string;
  source_job_id: string;
  company: string;
  title: string;
  department: string | null;
  city: string | null;
  location_text: string | null;
  job_type: string | null;
  recruitment_program: string | null;
  description: string | null;
  requirements: string[];
  published_at: string | null;
  status: string;
  source_method: string;
  verification_status: string;
  verified_at: string | null;
  warnings: string[];
}

export interface SavedJob {
  id: string;
  list_type: "saved" | "to_apply";
  note: string | null;
  created_at: string;
  job: JobListItem;
}

export interface ApplicationEvent {
  id: string;
  application_id: string;
  previous_status: string | null;
  new_status: string;
  from_status: string | null;
  to_status: string;
  event_time: string;
  created_at: string;
  actor: string;
  evidence_type: string;
  source_type: string;
  source_reference: string | null;
  evidence_summary: string | null;
  verification_status: string;
  note: string | null;
  /** True only for explicit assessment/interview appointments. */
  is_scheduled: boolean;
  /** Set when the slot was rescheduled or cancelled; kept for the audit trail. */
  superseded_at: string | null;
}

export interface ApplicationDetail extends ApplicationRecord {
  events: ApplicationEvent[];
}

export interface ApplicationRecord {
  id: string;
  status: string;
  applied_at: string | null;
  last_confirmed_at: string | null;
  needs_review: boolean;
  stale_days: number | null;
  notes: string | null;
  source_of_truth: string;
  source_type: string;
  source_reference: string | null;
  external_company: string | null;
  external_title: string | null;
  external_url: string | null;
  created_at: string;
  updated_at: string;
  job: JobListItem | null;
  lead: JobLead | null;
  latest_event: ApplicationEvent | null;
}

export interface ApplicationImportPreview {
  id: string;
  status: "ready" | "needs_review" | "confirmed" | "discarded";
  filename: string;
  subject: string | null;
  sender: string | null;
  received_at: string | null;
  parsed_company: string | null;
  parsed_title: string | null;
  parsed_status: string | null;
  parsed_event_time: string | null;
  confidence: number;
  matched_application_id: string | null;
  confirmed_event_id: string | null;
  body_excerpt: string | null;
  warnings: string[];
  duplicate: boolean;
  requires_confirmation: boolean;
  confirmed_at: string | null;
  created_at: string;
}

export interface EducationItem {
  school: string | null;
  degree: string | null;
  major: string | null;
  start_year: number | null;
  graduation_year: number | null;
}

export interface ExperienceItem {
  kind: string;
  title: string | null;
  time_range: string | null;
  skills: string[];
  description: string | null;
}

export interface JobPreferences {
  cities: string[];
  job_types: string[];
  keywords: string[];
  excluded_keywords: string[];
  target_companies: string[];
  target_roles: string[];
  available_start_date: string | null;
  internship_duration_months: number | null;
  internship_days_per_week: number | null;
  graduation_year: number | null;
  remote_ok: boolean | null;
}

export interface Profile {
  user_id: string;
  headline: string | null;
  education: EducationItem[];
  skills: string[];
  experiences: ExperienceItem[];
  projects: { title: string; time_range: string | null; summary: string | null }[];
  preferences: JobPreferences;
  version: number;
  verified_by_user: boolean;
  confirmed_at: string | null;
  updated_at: string | null;
}

export interface ProfileUpdatePayload {
  headline?: string | null;
  education?: EducationItem[];
  skills?: string[];
  experiences?: ExperienceItem[];
  projects?: { title: string; time_range?: string | null; summary: string | null }[];
  preferences?: Partial<JobPreferences>;
  verified_by_user?: boolean;
}

export interface ResumeParsed {
  name: string | null;
  email: string | null;
  phone: string | null;
  education: EducationItem[];
  skills: string[];
  experiences: ExperienceItem[];
  text_length: number;
  is_scan_like: boolean;
  warnings: string[];
}

export interface Resume {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  parse_status: string;
  parsed: ResumeParsed;
  error: string | null;
  is_primary: boolean;
  created_at: string;
}

export interface MatchResultRead {
  job_id: string | null;
  scorer_version: string;
  match_level: string;
  match_score: number | null;
  eligibility_status: string;
  eligibility_reasons: string[];
  matched_skills: string[];
  unverified_skills: string[];
  strengths: string[];
  gaps: string[];
  evidence_coverage: number;
  explanation: string;
}

export interface RecommendationItem {
  job: JobListItem;
  match: MatchResultRead;
  saved: boolean;
  applied_status: string | null;
}

export interface AgentThread {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AgentMessage {
  role: string;
  content: string;
  /**
   * Result cards produced by the same turn as this answer. Cards live on the
   * message instead of a page-level panel so they never drift below a newer
   * question or disappear when another turn finishes.
   */
  cards?: AgentRunResult["structured"] | null;
}

export interface DashboardCounts {
  saved: number;
  planned: number;
  applied: number;
  screening: number;
  assessment: number;
  interview: number;
  offer: number;
  needs_review: number;
}

export interface DashboardCalendarEvent {
  id: string;
  application_id: string;
  company: string;
  title: string;
  status: string;
  starts_at: string;
  source_type: string;
  verification_status: string;
}

export interface DashboardCalendar {
  events: DashboardCalendarEvent[];
  range_start: string;
  range_end: string;
  generated_at: string;
}

export interface DashboardSummary {
  counts: DashboardCounts;
  latest_jobs: {
    id: string;
    company: string;
    title: string;
    city: string | null;
    job_type: string | null;
    source_url: string;
    verification_status: string;
    published_at: string | null;
    first_seen_at: string;
  }[];
  recent_events: {
    id: string;
    application_id: string;
    company: string;
    title: string;
    status: string;
    event_time: string | null;
    source_type: string;
    evidence_type: string;
    verification_status: string;
    summary: string | null;
  }[];
  upcoming_events: {
    application_id: string;
    company: string;
    title: string;
    status: string;
    starts_at: string;
    source_type: string;
    verification_status: string;
  }[];
  generated_at: string;
  date: string;
}

export interface AgentRunResult {
  thread_id: string;
  status: string;
  intent: string | null;
  constraints: Record<string, unknown> | null;
  plan: { step: number; agent: string; status: string }[] | null;
  agent_results: Record<string, string> | null;
  final_answer: string | null;
  errors: string[];
  structured?: {
    jobs: AgentJobCard[];
    matches: AgentMatchCard[];
    /** Matches excluded by this turn's company/city/direction constraints. */
    extra_matches?: (AgentMatchCard & { selection_reason?: string })[];
    applications: AgentApplicationCard[];
    progress_events: {
      status?: string;
      event_time?: string | null;
      source_type?: string;
      appointment?: boolean;
      is_scheduled?: boolean;
      appointment_state?: "active" | "inactive" | null;
      superseded_at?: string | null;
    }[];
  } | null;
}

export interface AgentJobCard {
  id?: string;
  company?: string;
  title?: string;
  city?: string | null;
  job_type?: string | null;
  /** Verified Job field. */
  source_url?: string;
  /** JobLead field. */
  official_url?: string;
  verification_status?: string;
}

export interface AgentMatchCard {
  job?: { id?: string; company?: string; title?: string; city?: string | null; source_url?: string };
  match?: {
    match_score?: number | null;
    eligibility_status?: string;
    matched_skills?: string[];
    unverified_skills?: string[];
    explanation?: string;
  };
  applied_status?: string | null;
}

export interface AgentApplicationCard {
  id?: string;
  company?: string | null;
  title?: string | null;
  status?: string;
  applied_at?: string | null;
}

interface RawResponse {
  ok: boolean;
  status: number;
  body: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function fetchJson(
  path: string,
  options: { cookie?: string; timeoutMs?: number } = {},
): Promise<RawResponse | null> {
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(options.cookie ? { cookie: options.cookie } : {}),
      },
      signal: AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS),
    });
    const body: unknown = await response.json().catch(() => null);
    return { ok: response.ok, status: response.status, body };
  } catch {
    return null;
  }
}

export function toApiError(body: unknown, status: number): ApiErrorInfo {
  if (isRecord(body) && isRecord(body.error) && typeof body.error.code === "string") {
    return {
      code: body.error.code,
      message: typeof body.error.message === "string" ? body.error.message : "请求失败",
      status,
      details: isRecord(body.error.details) ? body.error.details : undefined,
    };
  }
  return { code: "UNEXPECTED_RESPONSE", message: "API 返回了无法识别的响应", status };
}

function isSystemInfo(value: unknown): value is SystemInfo {
  return (
    isRecord(value) &&
    typeof value.version === "string" &&
    typeof value.app_env === "string" &&
    typeof value.demo_mode === "boolean" &&
    (value.execution_mode === "llm" || value.execution_mode === "rule_fallback") &&
    typeof value.api_docs_url === "string"
  );
}

function isDependencyCheck(value: unknown): value is DependencyCheck {
  return (
    isRecord(value) &&
    typeof value.name === "string" &&
    (value.status === "ok" || value.status === "error")
  );
}

function extractChecks(body: unknown): DependencyCheck[] {
  if (!isRecord(body) || !isRecord(body.error) || !isRecord(body.error.details)) {
    return [];
  }
  const checks = body.error.details.checks;
  return Array.isArray(checks) ? checks.filter(isDependencyCheck) : [];
}

function isSessionUser(value: unknown): value is SessionUser {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.email === "string" &&
    typeof value.created_at === "string"
  );
}

function parsePage<T>(body: unknown): Page<T> | null {
  if (!isRecord(body) || !Array.isArray(body.data) || !isRecord(body.meta)) {
    return null;
  }
  const { page, page_size, total } = body.meta;
  if (
    typeof page !== "number" ||
    typeof page_size !== "number" ||
    typeof total !== "number"
  ) {
    return null;
  }
  return { data: body.data as T[], meta: { page, page_size, total } };
}

function isJobListItemShallow(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.source_url === "string" &&
    typeof value.is_demo === "boolean"
  );
}

export async function fetchSystemInfo(): Promise<ApiResult<SystemInfo>> {
  const result = await fetchJson("/api/v1/system/info");
  if (!result) {
    return { ok: false, error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" } };
  }
  if (!result.ok) {
    return { ok: false, error: toApiError(result.body, result.status) };
  }
  if (!isSystemInfo(result.body)) {
    return { ok: false, error: { code: "UNEXPECTED_RESPONSE", message: "API 响应字段不完整" } };
  }
  return { ok: true, data: result.body };
}

export async function fetchReadiness(): Promise<ReadinessSnapshot> {
  const result = await fetchJson("/readyz");
  if (!result) {
    return {
      reachable: false,
      ready: false,
      checks: [],
      checkedAt: null,
      error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" },
    };
  }

  const body = result.body;
  if (result.ok && isRecord(body) && body.status === "ready" && Array.isArray(body.checks)) {
    return {
      reachable: true,
      ready: true,
      checks: body.checks.filter(isDependencyCheck),
      checkedAt: typeof body.checked_at === "string" ? body.checked_at : null,
      error: null,
    };
  }

  return {
    reachable: true,
    ready: false,
    checks: extractChecks(body),
    checkedAt: null,
    error: toApiError(body, result.status),
  };
}

export async function fetchCurrentUser(cookie: string): Promise<SessionUser | null> {
  const result = await fetchJson("/api/v1/auth/me", { cookie });
  if (!result || !result.ok || !isRecord(result.body) || !isSessionUser(result.body.data)) {
    return null;
  }
  return result.body.data;
}

export async function fetchJobLeads(
  cookie: string,
  filters: { query?: string; company?: string } = {},
): Promise<ApiResult<JobLead[]>> {
  const query = new URLSearchParams();
  if (filters.query) query.set("query", filters.query);
  if (filters.company) query.set("company", filters.company);
  const suffix = query.toString();
  const result = await fetchJson(`/api/v1/job-leads${suffix ? `?${suffix}` : ""}`, { cookie });
  if (!result) {
    return { ok: false, error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" } };
  }
  if (!result.ok) {
    return { ok: false, error: toApiError(result.body, result.status) };
  }
  const data = isRecord(result.body) ? result.body.data : null;
  if (!Array.isArray(data)) {
    return {
      ok: false,
      error: { code: "UNEXPECTED_RESPONSE", message: "候选线索数据格式不正确" },
    };
  }
  return { ok: true, data: data as JobLead[] };
}

export async function fetchJobs(
  filters: JobFilters,
  cookie: string,
  pageSize = 12,
): Promise<ApiResult<Page<JobListItem>>> {
  const query = buildJobQuery(filters, pageSize);
  const result = await fetchJson(`/api/v1/jobs?${query}`, { cookie });
  if (!result) {
    return { ok: false, error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" } };
  }
  if (!result.ok) {
    return { ok: false, error: toApiError(result.body, result.status) };
  }
  const page = parsePage<JobListItem>(result.body);
  if (!page || !page.data.every(isJobListItemShallow)) {
    return { ok: false, error: { code: "UNEXPECTED_RESPONSE", message: "岗位数据格式不正确" } };
  }
  return { ok: true, data: page };
}

export async function fetchJob(
  jobId: string,
  cookie: string,
): Promise<ApiResult<JobDetail>> {
  const result = await fetchJson(`/api/v1/jobs/${jobId}`, { cookie });
  if (!result) {
    return { ok: false, error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" } };
  }
  if (!result.ok) {
    return { ok: false, error: toApiError(result.body, result.status) };
  }
  if (!isRecord(result.body) || !isRecord(result.body.data)) {
    return { ok: false, error: { code: "UNEXPECTED_RESPONSE", message: "岗位数据格式不正确" } };
  }
  return { ok: true, data: result.body.data as unknown as JobDetail };
}

export async function fetchSavedJobs(
  cookie: string,
  options: { list_type?: string; page?: number; page_size?: number } = {},
): Promise<ApiResult<Page<SavedJob>>> {
  const params = new URLSearchParams();
  if (options.list_type) {
    params.set("list_type", options.list_type);
  }
  params.set("page", String(options.page ?? 1));
  params.set("page_size", String(options.page_size ?? 20));
  const result = await fetchJson(`/api/v1/saved-jobs?${params.toString()}`, { cookie });
  if (!result) {
    return { ok: false, error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" } };
  }
  if (!result.ok) {
    return { ok: false, error: toApiError(result.body, result.status) };
  }
  const page = parsePage<SavedJob>(result.body);
  if (!page) {
    return { ok: false, error: { code: "UNEXPECTED_RESPONSE", message: "收藏数据格式不正确" } };
  }
  return { ok: true, data: page };
}

export async function fetchApplications(
  cookie: string,
  options: {
    status?: string;
    company?: string;
    query?: string;
    page?: number;
    page_size?: number;
  } = {},
): Promise<ApiResult<Page<ApplicationRecord>>> {
  const params = new URLSearchParams();
  if (options.status) {
    params.set("status", options.status);
  }
  if (options.company) {
    params.set("company", options.company);
  }
  if (options.query) {
    params.set("query", options.query);
  }
  params.set("page", String(options.page ?? 1));
  params.set("page_size", String(options.page_size ?? 20));
  const result = await fetchJson(`/api/v1/applications?${params.toString()}`, { cookie });
  if (!result) {
    return { ok: false, error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" } };
  }
  if (!result.ok) {
    return { ok: false, error: toApiError(result.body, result.status) };
  }
  const page = parsePage<ApplicationRecord>(result.body);
  if (!page) {
    return { ok: false, error: { code: "UNEXPECTED_RESPONSE", message: "投递数据格式不正确" } };
  }
  return { ok: true, data: page };
}

export interface MailboxConnection {
  id: string;
  provider: string;
  email_address: string;
  status: string;
  sync_enabled: boolean;
  last_sync_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface MailboxSyncRun {
  id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  scanned_count: number;
  candidate_count: number;
  duplicate_count: number;
  error_count: number;
  error_summary: string | null;
}

export interface RecruitmentCandidate {
  id: string;
  provider: string;
  matched_application_id: string | null;
  parsed_company: string | null;
  parsed_title: string | null;
  parsed_status: string | null;
  event_time: string | null;
  scheduled_event_time: string | null;
  confidence: number;
  evidence_summary: string | null;
  review_status: string;
  conflict_kind: string;
  conflict_reason: string | null;
  created_at: string;
}

export interface GmailAuthorize {
  configured: boolean;
  authorize_url: string | null;
  message: string;
}

export interface MailboxDeleteResult {
  provider: string;
  local_credentials_deleted: boolean;
  remote_revoked: boolean | null;
  message: string;
}

export interface AgentRun {
  id: string;
  thread_id: string;
  request_id: string;
  status: string;
  /** The question this run answered; null for HITL resume runs. */
  input_message?: string | null;
  result: AgentRunResult | null;
  error_code: string | null;
  error_summary: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested_at: string | null;
  attempt_count: number;
}

export interface AgentRunEventItem {
  sequence: number;
  event_type: string;
  safe_payload: Record<string, unknown>;
  created_at: string;
}

export interface TencentImportJob {
  title: string;
  city: string | null;
  cities: string | null;
  job_type: string | null;
  project: string | null;
  department: string | null;
  source_url: string;
}

export interface TencentImportResult {
  company: string;
  project: string;
  keyword: string;
  matched: number;
  created: number;
  updated: number;
  unchanged: number;
  jobs: TencentImportJob[];
  failures: { postId: string; reason: string }[];
}

export interface OfficialSourceInfo {
  key: string;
  label: string;
  mode: "api" | "rendered";
  note: string;
}

export interface OfficialSearchCompany {
  key: string;
  label: string;
  mode: "api" | "rendered";
  fetched: number;
  created: number;
  updated: number;
  unchanged: number;
  error: string | null;
}

export interface OfficialSearchJob {
  company: string;
  title: string;
  city: string | null;
  job_type: string | null;
  recruitment_program: string | null;
  source_url: string;
  jd_length: number;
  requirements: number;
}

export interface LinkPreview {
  url: string;
  final_url: string;
  title: string | null;
  company: string | null;
  city: string | null;
  location_text: string | null;
  job_type: string | null;
  description: string | null;
  requirements: string[];
  additional_info: string;
  warnings: string[];
  source: "rendered";
}

export interface OfficialSourceCompany {
  key: string;
  label: string;
  /** False = listed but not wired yet; UI must not pretend it works. */
  supported: boolean;
  mode: "api" | "rendered" | "none";
  note: string;
  /** Official search page to open when direct search is not wired yet. */
  search_page?: string;
}

export interface OfficialSearchResult {
  keyword: string;
  created: number;
  updated: number;
  unchanged: number;
  companies: OfficialSearchCompany[];
  jobs: OfficialSearchJob[];
}
