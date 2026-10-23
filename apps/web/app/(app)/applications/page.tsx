import { cookies } from "next/headers";
import Link from "next/link";
import { ArrowUpRight, CircleAlert, ClipboardList, Search } from "lucide-react";

import { ApplicationStatusControl } from "@/components/application-status-control";
import { ApplicationTimeline } from "@/components/application-timeline";
import { CreateApplicationButton } from "@/components/create-application-button";
import { EmailImportPanel } from "@/components/email-import-panel";
import { EmailSyncCenter } from "@/components/email-sync-center";
import { LinkApplicationForm } from "@/components/link-application-form";
import { StatusPill } from "@/components/status-pill";
import { fetchApplications, fetchSavedJobs } from "@/lib/api";
import type { ApplicationRecord } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  APPLICATION_STATUS_OPTIONS,
  formatApplicationSource,
  formatApplicationStatus,
  formatEventVerification,
  formatJobType,
} from "@/lib/job-display";

export const dynamic = "force-dynamic";

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function titleOf(application: ApplicationRecord): string {
  return (
    application.job?.title ??
    application.lead?.title ??
    application.external_title ??
    "未命名岗位"
  );
}

function companyOf(application: ApplicationRecord): string {
  return (
    application.job?.company ??
    application.lead?.company ??
    application.external_company ??
    "公司未知"
  );
}

function officialUrlOf(application: ApplicationRecord): string | null {
  return application.external_url ?? application.job?.source_url ?? application.lead?.official_url ?? null;
}

export default async function ApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const filters = {
    status: firstValue(params.status),
    company: firstValue(params.company),
    query: firstValue(params.query),
    view: firstValue(params.view) || "list",
  };
  const view = ["list", "table", "kanban"].includes(filters.view) ? filters.view : "list";
  const filterQuery = new URLSearchParams(
    Object.entries({
      query: filters.query,
      company: filters.company,
      status: filters.status,
    }).filter(([, value]) => Boolean(value)) as [string, string][],
  );
  const cookie = (await cookies()).toString();
  const [candidates, applications] = await Promise.all([
    fetchSavedJobs(cookie, { list_type: "to_apply", page_size: 50 }),
    fetchApplications(cookie, {
      status: filters.status || undefined,
      company: filters.company || undefined,
      query: filters.query || undefined,
      page_size: 50,
    }),
  ]);
  const applicationRows = applications.ok ? applications.data.data : [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            个人申请进度
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            官网申请由你自行完成；CareerPilot 只记录你确认的进度、证据和时间线，不会自动投递。
          </p>
        </div>
        <StatusPill tone="info">M2-R2 · 手动/邮件确认</StatusPill>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <LinkApplicationForm />
        <span className="text-xs text-slate-500">
          打开官网或收到邮件不会自动变成“已申请”，必须由你确认。
        </span>
      </div>

      <EmailSyncCenter applications={applicationRows} />

      <EmailImportPanel applications={applicationRows} />

      <form
        method="get"
        action="/applications"
        className="grid gap-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-12"
      >
        <div className="relative sm:col-span-5">
          <label htmlFor="query" className="sr-only">
            搜索岗位
          </label>
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400"
            aria-hidden
          />
          <input
            id="query"
            name="query"
            defaultValue={filters.query}
            placeholder="搜索岗位名称"
            className="w-full rounded-lg border border-slate-300 py-2 pr-3 pl-9 text-sm"
          />
        </div>
        <input
          name="company"
          defaultValue={filters.company}
          placeholder="企业"
          aria-label="企业"
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm sm:col-span-3"
        />
        <select
          name="status"
          defaultValue={filters.status}
          aria-label="状态"
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm sm:col-span-2"
        >
          <option value="">全部状态</option>
          {APPLICATION_STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {formatApplicationStatus(status)}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white sm:col-span-2"
        >
          筛选
        </button>
      </form>

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">待投递岗位</h2>
            <p className="mt-0.5 text-xs text-slate-500">来自岗位详情页的“加入待投递”操作</p>
          </div>
          {candidates.ok ? (
            <span className="text-xs text-slate-500">{candidates.data.meta.total} 个岗位</span>
          ) : null}
        </div>

        {!candidates.ok ? (
          <ErrorRow message={candidates.error.message} code={candidates.error.code} />
        ) : candidates.data.data.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-slate-500">
            还没有待投递岗位。前往{" "}
            <Link href="/jobs" className="font-medium text-slate-800 underline">
              岗位库
            </Link>{" "}
            挑选岗位并加入清单。
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {candidates.data.data.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="min-w-0">
                  <Link
                    href={`/jobs/${row.job.id}`}
                    className="truncate text-sm font-medium text-slate-900 hover:text-sky-700"
                  >
                    {row.job.title}
                  </Link>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {row.job.company} · {row.job.city ?? "城市未知"} ·{" "}
                    {formatJobType(row.job.job_type)}
                  </p>
                  {row.job.is_demo ? (
                    <span className="mt-1 inline-block text-[11px] text-amber-700">演示数据</span>
                  ) : null}
                </div>
                <CreateApplicationButton jobId={row.job.id} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
        {[
          { key: "list", label: "列表" },
          { key: "table", label: "表格" },
          { key: "kanban", label: "看板" },
        ].map((item) => {
          const params = new URLSearchParams(filterQuery);
          params.set("view", item.key);
          return (
            <Link
              key={item.key}
              href={`/applications?${params.toString()}`}
              aria-current={view === item.key ? "page" : undefined}
              className={`rounded-md px-3 py-1 text-xs ${
                view === item.key ? "bg-slate-900 text-white" : "text-slate-600"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">申请记录</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              状态、来源、证据和最近确认时间均保留；超过 14 天未确认会提示待核实。
            </p>
          </div>
          {applications.ok ? (
            <span className="text-xs text-slate-500">{applications.data.meta.total} 条记录</span>
          ) : null}
        </div>

        {!applications.ok ? (
          <ErrorRow message={applications.error.message} code={applications.error.code} />
        ) : applications.data.data.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-10 text-center">
            <div className="flex size-11 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
              <ClipboardList className="size-5" aria-hidden />
            </div>
            <p className="mt-3 text-sm text-slate-600">还没有申请记录</p>
            <p className="mt-1 max-w-md text-xs leading-relaxed text-slate-500">
              可从待投递岗位登记，或使用“仅登记官方链接”/邮件导入建立真实进度。
            </p>
          </div>
        ) : view === "kanban" ? (
          <ApplicationKanban applications={applications.data.data} />
        ) : view === "table" ? (
          <ApplicationTable applications={applications.data.data} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {applications.data.data.map((application) => {
              const title = titleOf(application);
              const company = companyOf(application);
              const url = officialUrlOf(application);
              const jobId = application.job?.id;
              return (
                <li key={application.id} className="px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      {jobId ? (
                        <Link
                          href={`/jobs/${jobId}`}
                          className="inline-flex items-center gap-1 text-sm font-medium text-slate-900 hover:text-sky-700"
                        >
                          {title}
                          <ArrowUpRight className="size-3 text-slate-400" aria-hidden />
                        </Link>
                      ) : (
                        <span className="text-sm font-medium text-slate-900">{title}</span>
                      )}
                      <p className="mt-0.5 text-xs text-slate-500">
                        {company} · {application.job?.city ?? "城市未知"} ·{" "}
                        {formatJobType(application.job?.job_type ?? null)}
                      </p>
                    </div>
                    <ApplicationStatusControl
                      applicationId={application.id}
                      currentStatus={application.status}
                    />
                  </div>

                  <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-slate-500">
                    <div className="flex gap-1">
                      <dt>当前状态</dt>
                      <dd className="font-medium text-slate-700">
                        {formatApplicationStatus(application.status)}
                      </dd>
                    </div>
                    <div className="flex gap-1">
                      <dt>来源</dt>
                      <dd>{formatApplicationSource(application.source_type)}</dd>
                    </div>
                    <div className="flex gap-1">
                      <dt>最近确认</dt>
                      <dd>
                        {application.last_confirmed_at
                          ? formatDateTime(application.last_confirmed_at)
                          : "未确认"}
                      </dd>
                    </div>
                    {application.needs_review ? (
                      <div className="flex gap-1 text-amber-700">
                        <dt>待核实</dt>
                        <dd>{application.stale_days ?? 0} 天未确认</dd>
                      </div>
                    ) : null}
                    {application.job?.is_demo ? (
                      <dd className="text-amber-700">演示岗位</dd>
                    ) : null}
                  </dl>

                  {application.latest_event ? (
                    <p className="mt-2 text-xs text-slate-500">
                      最近事件：{formatApplicationStatus(application.latest_event.new_status)}
                      {" · "}
                      {formatApplicationSource(application.latest_event.source_type)}
                      {" · "}
                      {formatEventVerification(application.latest_event.verification_status)}
                      {" · "}
                      {formatDateTime(application.latest_event.event_time)}
                    </p>
                  ) : null}

                  {application.notes ? (
                    <p className="mt-2 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
                      {application.notes}
                    </p>
                  ) : null}

                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    {url ? (
                      <a
                        href={url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-xs font-medium text-sky-700 hover:underline"
                      >
                        查看官网
                      </a>
                    ) : null}
                    <ApplicationTimeline applicationId={application.id} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function ErrorRow({ message, code }: { message: string; code: string }) {
  return (
    <div className="flex items-start gap-2 px-5 py-6 text-sm text-rose-700">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>
        {message}（{code}）
      </span>
    </div>
  );
}


const KANBAN_COLUMNS: { key: string; label: string; statuses: string[] }[] = [
  { key: "planned", label: "计划申请", statuses: ["planned", "to_apply", "preparing"] },
  { key: "applied", label: "已申请", statuses: ["applied"] },
  { key: "screening", label: "筛选中", statuses: ["screening"] },
  { key: "assessment", label: "笔试/测评", statuses: ["assessment", "online_assessment"] },
  { key: "interview", label: "面试中", statuses: ["interview"] },
  { key: "offer", label: "Offer", statuses: ["offer"] },
  {
    key: "closed",
    label: "未通过/撤回",
    statuses: ["rejected", "withdrawn", "closed", "unknown"],
  },
];

function ApplicationKanban({ applications }: { applications: ApplicationRecord[] }) {
  return (
    <div className="grid gap-3 overflow-x-auto p-4 md:grid-cols-4 xl:grid-cols-7">
      {KANBAN_COLUMNS.map((column) => {
        const rows = applications.filter((item) => column.statuses.includes(item.status));
        return (
          <div key={column.key} className="rounded-xl border border-slate-200 bg-slate-50/60">
            <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
              <span className="text-xs font-medium text-slate-700">{column.label}</span>
              <span className="text-[11px] text-slate-400">{rows.length}</span>
            </div>
            <div className="space-y-2 p-2">
              {rows.length === 0 ? (
                <p className="py-3 text-center text-[11px] text-slate-400">暂无</p>
              ) : (
                rows.map((application) => (
                  <article key={application.id} className="rounded-lg border border-slate-200 bg-white p-2.5">
                    <Link
                      href={`/applications/${application.id}`}
                      className="block truncate text-xs font-medium text-slate-800 hover:text-sky-700"
                    >
                      {titleOf(application)}
                    </Link>
                    <p className="mt-0.5 truncate text-[11px] text-slate-500">{companyOf(application)}</p>
                    <p className="mt-1 text-[10px] text-slate-400">
                      {application.last_confirmed_at
                        ? `确认 ${formatDateTime(application.last_confirmed_at)}`
                        : "未确认"}
                    </p>
                  </article>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ApplicationTable({ applications }: { applications: ApplicationRecord[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-4 py-2 font-medium">公司</th>
            <th className="px-4 py-2 font-medium">岗位</th>
            <th className="px-4 py-2 font-medium">状态</th>
            <th className="px-4 py-2 font-medium">来源</th>
            <th className="px-4 py-2 font-medium">最近确认</th>
            <th className="px-4 py-2 font-medium">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {applications.map((application) => (
            <tr key={application.id} className="hover:bg-slate-50">
              <td className="px-4 py-2 text-slate-700">{companyOf(application)}</td>
              <td className="px-4 py-2 font-medium text-slate-900">{titleOf(application)}</td>
              <td className="px-4 py-2 text-slate-700">
                {formatApplicationStatus(application.status)}
                {application.needs_review ? (
                  <span className="ml-1 text-[10px] text-amber-700">待核实</span>
                ) : null}
              </td>
              <td className="px-4 py-2 text-slate-600">
                {formatApplicationSource(application.source_type)}
              </td>
              <td className="px-4 py-2 text-slate-600">
                {application.last_confirmed_at
                  ? formatDateTime(application.last_confirmed_at)
                  : "未确认"}
              </td>
              <td className="px-4 py-2">
                <Link href={`/applications/${application.id}`} className="text-sky-700 hover:underline">
                  详情
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
