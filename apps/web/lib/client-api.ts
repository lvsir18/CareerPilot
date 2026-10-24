"use client";

/**
 * Browser-side API client. All writes go through the authenticated cookie and
 * every result is returned as a value so forms can render explicit errors.
 */

import {
  toApiError,
  type AgentMessage,
  type AgentRun,
  type AgentRunEventItem,
  type AgentRunResult,
  type AgentThread,
  type ApiResult,
  type ApplicationDetail,
  type ApplicationEvent,
  type ApplicationImportPreview,
  type ApplicationRecord,
  type DashboardCalendar,
  type DashboardSummary,
  type DiscoveryResponse,
  type JobDetail,
  type JobImportPreview,
  type GmailAuthorize,
  type MailboxDeleteResult,
  type JobLead,
  type JobLeadDetail,
  type MailboxConnection,
  type MailboxSyncRun,
  type Profile,
  type ProfileUpdatePayload,
  type RecruitmentCandidate,
  type RecommendationItem,
  type Resume,
  type SavedJob,
  type SessionUser,
  type OfficialSearchResult,
  type TencentImportResult,
} from "@/lib/api";

const CLIENT_TIMEOUT_MS = 6000;

function clientBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ?? "http://localhost:8000"
  );
}

interface RequestOptions {
  /** Per-request override; long-running agent runs need minutes. */
  timeoutMs?: number;
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
}

const CSRF_COOKIE = "careerpilot_csrf";
const CSRF_HEADER = "X-CSRF-Token";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const prefix = `${name}=`;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

async function ensureCsrfToken(): Promise<string | null> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) {
    return existing;
  }
  try {
    const response = await fetch(`${clientBaseUrl()}/api/v1/auth/csrf`, {
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    const body: unknown = await response.json().catch(() => null);
    if (body && typeof body === "object" && "data" in body) {
      const data = (body as { data?: { csrf_token?: unknown } }).data;
      if (data && typeof data.csrf_token === "string") {
        return data.csrf_token;
      }
    }
  } catch {
    return null;
  }
  return readCookie(CSRF_COOKIE);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const method = options.method ?? "GET";
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  const csrfToken = unsafe ? await ensureCsrfToken() : null;
  try {
    const response = await fetch(`${clientBaseUrl()}${path}`, {
      method,
      credentials: "include",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(csrfToken ? { [CSRF_HEADER]: csrfToken } : {}),
        ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(options.timeoutMs ?? CLIENT_TIMEOUT_MS),
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      return { ok: false, error: toApiError(body, response.status) };
    }
    if (body && typeof body === "object" && "data" in body) {
      return { ok: true, data: (body as { data: T }).data };
    }
    return { ok: true, data: undefined as T };
  } catch (error) {
    const timedOut =
      error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError");
    return {
      ok: false,
      error: timedOut
        ? { code: "TIMEOUT", message: "请求超时：检索耗时较长，请稍后重试或缩小范围" }
        : { code: "NETWORK_ERROR", message: "无法连接 API 服务" },
    };
  }
}

export function login(email: string, password: string): Promise<ApiResult<SessionUser>> {
  return request<SessionUser>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export function register(email: string, password: string): Promise<ApiResult<SessionUser>> {
  return request<SessionUser>("/api/v1/auth/register", {
    method: "POST",
    body: { email, password },
  });
}

export function logout(): Promise<ApiResult<undefined>> {
  return request<undefined>("/api/v1/auth/logout", { method: "POST" });
}

export function saveJob(
  jobId: string,
  listType: "saved" | "to_apply",
): Promise<ApiResult<SavedJob>> {
  return request<SavedJob>(`/api/v1/jobs/${jobId}/save`, {
    method: "POST",
    body: { list_type: listType },
  });
}

export function unsaveJob(
  jobId: string,
  listType: "saved" | "to_apply",
): Promise<ApiResult<undefined>> {
  return request<undefined>(
    `/api/v1/jobs/${jobId}/save?list_type=${encodeURIComponent(listType)}`,
    { method: "DELETE" },
  );
}

export interface ApplicationTargetPayload {
  job_id?: string;
  job_lead_id?: string;
  external_company?: string;
  external_title?: string;
  external_url?: string;
  status?: string;
  notes?: string;
  applied_at?: string;
}

export function createApplicationRecord(
  payload: ApplicationTargetPayload,
): Promise<ApiResult<ApplicationRecord>> {
  return request<ApplicationRecord>("/api/v1/applications", {
    method: "POST",
    body: payload,
  });
}

export function createApplication(
  jobId: string,
  status = "preparing",
): Promise<ApiResult<ApplicationRecord>> {
  return createApplicationRecord({ job_id: jobId, status });
}

export function deleteApplication(applicationId: string): Promise<ApiResult<undefined>> {
  return request<undefined>(`/api/v1/applications/${applicationId}`, { method: "DELETE" });
}

export function fetchApplicationDetail(
  applicationId: string,
): Promise<ApiResult<ApplicationDetail>> {
  return request<ApplicationDetail>(`/api/v1/applications/${applicationId}`);
}

export function updateApplicationMetadata(
  applicationId: string,
  payload: {
    notes?: string;
    external_company?: string;
    external_title?: string;
    external_url?: string;
  },
): Promise<ApiResult<ApplicationRecord>> {
  return request<ApplicationRecord>(`/api/v1/applications/${applicationId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function addApplicationEvent(
  applicationId: string,
  payload: {
    status: string;
    event_time?: string;
    note?: string;
    evidence_summary?: string;
    source_reference?: string;
    /** Retire only the selected appointment; preserve other rounds. */
    reschedule_event_id?: string;
    /** Legacy: allowed only if one active appointment of this kind exists. */
    supersede_scheduled?: boolean;
  },
): Promise<ApiResult<ApplicationEvent>> {
  return request<ApplicationEvent>(`/api/v1/applications/${applicationId}/events`, {
    method: "POST",
    body: payload,
  });
}

export function cancelApplicationEvent(
  applicationId: string,
  eventId: string,
): Promise<ApiResult<ApplicationEvent>> {
  return request<ApplicationEvent>(
    `/api/v1/applications/${applicationId}/events/${eventId}/cancel`,
    { method: "POST", body: {} },
  );
}

export function updateApplicationStatus(
  applicationId: string,
  status: string,
  note?: string,
): Promise<ApiResult<unknown>> {
  return request(`/api/v1/applications/${applicationId}/status`, {
    method: "PATCH",
    body: { status, ...(note ? { note } : {}) },
  });
}

export function previewJobImport(url: string): Promise<ApiResult<JobImportPreview>> {
  return request<JobImportPreview>("/api/v1/job-imports/preview", {
    method: "POST",
    body: { url },
  });
}

export interface JobImportPayload {
  url: string;
  mode: "public_page" | "manual_paste";
  confirmed: boolean;
  company?: string;
  title?: string;
  description?: string;
  requirements?: string[];
  city?: string;
  location_text?: string;
  job_type?: string;
  recruitment_program?: string;
  published_at?: string;
}

export function importJob(payload: JobImportPayload): Promise<ApiResult<JobDetail>> {
  return request<JobDetail>("/api/v1/job-imports", {
    method: "POST",
    body: payload,
  });
}

export interface JobLeadImportPayload {
  url: string;
  title: string;
  description?: string;
  city?: string;
  job_type?: string;
  published_date?: string;
  company?: string;
}

export function importJobLead(
  payload: JobLeadImportPayload,
): Promise<ApiResult<JobLead>> {
  return request<JobLead>("/api/v1/job-leads/import", {
    method: "POST",
    body: payload,
  });
}

export interface DiscoverParams {
  query?: string;
  company?: string;
  companies?: string[];
  city?: string;
  job_type?: string;
  job_family?: string;
  verification?: string;
  published_within_days?: number;
  days?: number;
  sort?: string;
  page?: number;
  page_size?: number;
  limit?: number;
}

export function discoverJobs(
  params: DiscoverParams,
): Promise<ApiResult<DiscoveryResponse>> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (key === "companies" && Array.isArray(value)) {
      if (value.length) {
        search.set("companies", value.join(","));
      }
      return;
    }
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  });
  // Discovery performs live provider queries on the server; a 20-query sweep
  // routinely needs 10-40s, so it must not share the default 6s budget.
  return request<DiscoveryResponse>(`/api/v1/jobs/discover?${search.toString()}`, {
    timeoutMs: 120_000,
  });
}

export function verifyJobLead(leadId: string): Promise<ApiResult<unknown>> {
  return request(`/api/v1/job-leads/${leadId}/verify`, { method: "POST" });
}

export function getJobLead(leadId: string): Promise<ApiResult<JobLeadDetail>> {
  return request<JobLeadDetail>(`/api/v1/job-leads/${leadId}`);
}

async function uploadRequest<T>(
  path: string,
  formData: FormData,
): Promise<ApiResult<T>> {
  const token = await ensureCsrfToken();
  try {
    const response = await fetch(`${clientBaseUrl()}${path}`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(token ? { [CSRF_HEADER]: token } : {}),
      },
      body: formData,
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      return { ok: false, error: toApiError(body, response.status) };
    }
    if (body && typeof body === "object" && "data" in body) {
      return { ok: true, data: (body as { data: T }).data };
    }
    return {
      ok: false,
      error: { code: "UNEXPECTED_RESPONSE", message: "服务器返回格式不正确" },
    };
  } catch {
    return { ok: false, error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" } };
  }
}

export function uploadApplicationEmail(
  file: File,
): Promise<ApiResult<ApplicationImportPreview>> {
  const form = new FormData();
  form.append("file", file, file.name);
  return uploadRequest<ApplicationImportPreview>("/api/v1/application-imports/email", form);
}

export function confirmApplicationImport(
  importId: string,
  payload: { application_id?: string; status?: string; event_time?: string; note?: string },
): Promise<ApiResult<ApplicationImportPreview>> {
  return request<ApplicationImportPreview>(
    `/api/v1/application-imports/${importId}/confirm`,
    { method: "POST", body: payload },
  );
}

export function uploadResume(file: File): Promise<ApiResult<Resume>> {
  const form = new FormData();
  form.append("file", file, file.name);
  return uploadRequest<Resume>("/api/v1/resumes", form);
}

export function listResumes(): Promise<ApiResult<Resume[]>> {
  return request<Resume[]>("/api/v1/resumes");
}

export function deleteResume(resumeId: string): Promise<ApiResult<undefined>> {
  return request<undefined>(`/api/v1/resumes/${resumeId}`, { method: "DELETE" });
}

export function setPrimaryResume(resumeId: string): Promise<ApiResult<Resume>> {
  return request<Resume>(`/api/v1/resumes/${resumeId}/primary`, { method: "POST" });
}

export function getProfile(): Promise<ApiResult<Profile>> {
  return request<Profile>("/api/v1/profile/me");
}

export function updateProfile(payload: ProfileUpdatePayload): Promise<ApiResult<Profile>> {
  return request<Profile>("/api/v1/profile/me", { method: "PATCH", body: payload });
}

export function confirmProfile(): Promise<ApiResult<Profile>> {
  return request<Profile>("/api/v1/profile/confirm", { method: "POST" });
}

export function applyResumeToProfile(resumeId: string): Promise<ApiResult<Profile>> {
  return request<Profile>("/api/v1/profile/apply-resume", {
    method: "POST",
    body: { resume_id: resumeId },
  });
}

export function matchJob(jobId: string): Promise<ApiResult<RecommendationItem>> {
  return request<RecommendationItem>(`/api/v1/matches/jobs/${jobId}`, { method: "POST" });
}

export function getRecommendations(
  params: { companies?: string[]; cities?: string[]; job_types?: string[]; exclude_applied?: boolean } = {},
): Promise<ApiResult<RecommendationItem[]>> {
  const search = new URLSearchParams();
  if (params.companies?.length) search.set("companies", params.companies.join(","));
  if (params.cities?.length) search.set("cities", params.cities.join(","));
  if (params.job_types?.length) search.set("job_types", params.job_types.join(","));
  if (params.exclude_applied) search.set("exclude_applied", "true");
  return request<RecommendationItem[]>(`/api/v1/matches/recommendations?${search.toString()}`);
}

export function createAgentThread(): Promise<ApiResult<AgentThread>> {
  return request<AgentThread>("/api/v1/agent/threads", { method: "POST" });
}

export function listAgentThreads(): Promise<ApiResult<AgentThread[]>> {
  return request<AgentThread[]>("/api/v1/agent/threads");
}

export function renameAgentThread(
  threadId: string,
  title: string,
): Promise<ApiResult<AgentThread>> {
  return request<AgentThread>(`/api/v1/agent/threads/${threadId}`, {
    method: "PATCH",
    body: { title },
  });
}

export function deleteAgentThread(threadId: string): Promise<ApiResult<undefined>> {
  return request<undefined>(`/api/v1/agent/threads/${threadId}`, { method: "DELETE" });
}

export function listAgentMessages(threadId: string): Promise<ApiResult<AgentMessage[]>> {
  return request<AgentMessage[]>(`/api/v1/agent/threads/${threadId}/messages`);
}

export function listAgentThreadRuns(
  threadId: string,
  limit = 5,
): Promise<ApiResult<AgentRun[]>> {
  return request<AgentRun[]>(`/api/v1/agent/threads/${threadId}/runs?limit=${limit}`);
}

export function runAgent(
  threadId: string,
  message: string,
): Promise<ApiResult<AgentRunResult>> {
  return request<AgentRunResult>(`/api/v1/agent/threads/${threadId}/runs`, {
    method: "POST",
    body: { message },
    // Multi-agent runs call the LLM and search providers several times.
    timeoutMs: 180_000,
  });
}

export function resumeAgent(
  threadId: string,
  approve: boolean,
): Promise<ApiResult<AgentRun>> {
  // Resume is async: the API requeues the run and returns it, the caller follows
  // the SSE stream instead of blocking on a synchronous graph execution.
  return request<AgentRun>(`/api/v1/agent/threads/${threadId}/resume`, {
    method: "POST",
    body: { approve },
  });
}

export function getDashboardSummary(): Promise<ApiResult<DashboardSummary>> {
  return request<DashboardSummary>("/api/v1/dashboard/summary");
}

export function getCalendarEvents(
  start?: string,
  end?: string,
): Promise<ApiResult<DashboardCalendar>> {
  const params = new URLSearchParams();
  if (start) params.set("from", start);
  if (end) params.set("to", end);
  const query = params.toString();
  return request<DashboardCalendar>(`/api/v1/dashboard/calendar${query ? `?${query}` : ""}`);
}

export function listMailboxes(): Promise<ApiResult<MailboxConnection[]>> {
  return request<MailboxConnection[]>("/api/v1/mailboxes");
}

export function connectQQMailbox(payload: {
  email_address: string;
  auth_code: string;
}): Promise<ApiResult<MailboxConnection>> {
  return request<MailboxConnection>("/api/v1/mailboxes/qq/connect", {
    method: "POST",
    body: payload,
  });
}

export function getGmailAuthorize(): Promise<ApiResult<GmailAuthorize>> {
  return request<GmailAuthorize>("/api/v1/mailboxes/gmail/authorize");
}

export function testMailbox(id: string): Promise<ApiResult<MailboxConnection>> {
  return request<MailboxConnection>(`/api/v1/mailboxes/${id}/test`, { method: "POST" });
}

export function syncMailbox(id: string): Promise<ApiResult<MailboxSyncRun>> {
  return request<MailboxSyncRun>(`/api/v1/mailboxes/${id}/sync`, { method: "POST" });
}

export function updateMailbox(
  id: string,
  payload: { sync_enabled?: boolean },
): Promise<ApiResult<MailboxConnection>> {
  return request<MailboxConnection>(`/api/v1/mailboxes/${id}`, { method: "PATCH", body: payload });
}

export function deleteMailbox(id: string): Promise<ApiResult<MailboxDeleteResult>> {
  return request<MailboxDeleteResult>(`/api/v1/mailboxes/${id}`, { method: "DELETE" });
}

export function listMailboxSyncRuns(id: string): Promise<ApiResult<MailboxSyncRun[]>> {
  return request<MailboxSyncRun[]>(`/api/v1/mailboxes/${id}/sync-runs`);
}

export function listRecruitmentCandidates(
  reviewStatus?: string,
): Promise<ApiResult<RecruitmentCandidate[]>> {
  const search = new URLSearchParams();
  if (reviewStatus) search.set("review_status", reviewStatus);
  const query = search.toString();
  return request<RecruitmentCandidate[]>(
    `/api/v1/recruitment-email-candidates${query ? `?${query}` : ""}`,
  );
}

export function confirmRecruitmentCandidate(
  id: string,
  payload: {
    application_id?: string;
    status?: string;
    event_time?: string;
    note?: string;
    keep_current?: boolean;
  },
): Promise<ApiResult<RecruitmentCandidate>> {
  return request<RecruitmentCandidate>(`/api/v1/recruitment-email-candidates/${id}/confirm`, {
    method: "POST",
    body: payload,
  });
}

export function discardRecruitmentCandidate(
  id: string,
): Promise<ApiResult<RecruitmentCandidate>> {
  return request<RecruitmentCandidate>(
    `/api/v1/recruitment-email-candidates/${id}/discard`,
    { method: "POST" },
  );
}

export function createAgentRun(payload: {
  thread_id: string;
  request_id: string;
  message: string;
}): Promise<ApiResult<AgentRun>> {
  return request<AgentRun>("/api/v1/agent/runs", {
    method: "POST",
    body: payload,
    timeoutMs: 30_000,
  });
}

export function getAgentRun(runId: string): Promise<ApiResult<AgentRun>> {
  return request<AgentRun>(`/api/v1/agent/runs/${runId}`);
}

export function getAgentRunEvents(
  runId: string,
  after = 0,
): Promise<ApiResult<AgentRunEventItem[]>> {
  return request<AgentRunEventItem[]>(
    `/api/v1/agent/runs/${runId}/events?after=${after}`,
  );
}

export function cancelAgentRun(runId: string): Promise<ApiResult<AgentRun>> {
  return request<AgentRun>(`/api/v1/agent/runs/${runId}/cancel`, { method: "POST" });
}

export function importTencentJobs(payload: {
  keyword?: string;
  project?: string;
  limit?: number;
}): Promise<ApiResult<TencentImportResult>> {
  return request<TencentImportResult>("/api/v1/tencent/jobs/import", {
    method: "POST",
    body: payload,
    timeoutMs: 90_000,
  });
}

export function searchOfficialJobs(payload: {
  companies: string[];
  keyword?: string;
  limit?: number;
  project?: string;
}): Promise<ApiResult<OfficialSearchResult>> {
  return request<OfficialSearchResult>("/api/v1/official/jobs/search", {
    method: "POST",
    body: payload,
    // Rendered sources open a real page per company (roughly 8-12s each).
    timeoutMs: 180_000,
  });
}
