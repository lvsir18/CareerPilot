import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowUpRight, CircleAlert, MapPin } from "lucide-react";

import { JobActions } from "@/components/job-actions";
import { JobMatchPanel } from "@/components/job-match-panel";
import { StatusPill } from "@/components/status-pill";
import { fetchJob, fetchSavedJobs } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  formatJobStatus,
  formatJobType,
  formatSourceType,
  formatVerificationStatus,
  jobStatusTone,
  verificationTone,
} from "@/lib/job-display";

export const dynamic = "force-dynamic";

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 py-2.5 last:border-b-0">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-right text-xs font-medium text-slate-800">{value}</dd>
    </div>
  );
}

export default async function JobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  // Opening a posting from 发现岗位 must return there (with its search state),
  // not jump to 岗位库 and lose the results.
  const query = (await searchParams) ?? {};
  const fromDiscover = String(query.from ?? "") === "discover";
  const backHref = fromDiscover ? "/discover" : "/jobs";
  const backLabel = fromDiscover ? "返回发现岗位" : "返回岗位库";
  const cookie = (await cookies()).toString();
  // Save state is a page-level fact: the sidebar button must offer "取消收藏"
  // on a job the user already saved, not a second "收藏".
  const [result, savedResult] = await Promise.all([
    fetchJob(id, cookie),
    fetchSavedJobs(cookie, { list_type: "saved", page_size: 50 }),
  ]);
  const isSaved =
    savedResult.ok && savedResult.data.data.some((item) => item.job.id === id);

  if (!result.ok) {
    if (result.error.status === 404) {
      notFound();
    }
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6">
        <div className="flex items-center gap-2 text-sm font-medium text-rose-800">
          <CircleAlert className="size-4" aria-hidden />
          岗位加载失败
        </div>
        <p className="mt-2 text-sm text-rose-700">
          {result.error.message}（{result.error.code}）
        </p>
        <Link
          href={backHref}
          className="mt-4 inline-flex text-sm font-medium text-rose-800 underline"
        >
          {backLabel}
        </Link>
      </div>
    );
  }

  const job = result.data;

  return (
    <div className="space-y-6">
      <Link
        href={backHref}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        {backLabel}
      </Link>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              {job.is_demo ? (
                <StatusPill tone="warning">演示数据</StatusPill>
              ) : (
                <StatusPill tone="neutral">真实来源</StatusPill>
              )}
              <StatusPill tone={jobStatusTone(job.status)}>
                来源状态：{formatJobStatus(job.status)}
              </StatusPill>
              <span className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-500 ring-1 ring-slate-200 ring-inset">
                {formatSourceType(job.source_type)}
              </span>
            </div>

            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">
              {job.title}
            </h1>
            <p className="mt-1 text-sm text-slate-600">{job.company}</p>
            {job.department || job.recruitment_program ? (
              <p className="mt-1 text-xs text-slate-400">
                {[job.department, job.recruitment_program].filter(Boolean).join(" · ")}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3.5" aria-hidden />
                {job.city ?? job.location_text ?? "城市未知"}
              </span>
              <span>{formatJobType(job.job_type)}</span>
              <span>
                发布时间：
                {job.published_at ? formatDateTime(job.published_at) : "未知（来源未提供）"}
              </span>
            </div>

            {job.is_demo ? (
              <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800">
                这是离线演示岗位，公司名与链接均为示例，不代表真实招聘信息。演示数据不会在{" "}
                <code className="font-mono">DEMO_MODE=false</code> 时返回。
              </p>
            ) : (
              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                <StatusPill tone={verificationTone(job.verification_status)}>
                  {formatVerificationStatus(job.verification_status)}
                </StatusPill>
                <span>
                  {job.verified_at
                    ? `核验时间：${formatDateTime(job.verified_at)}`
                    : "尚无核验时间"}
                </span>
              </div>
            )}
          </header>

          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">职位描述</h2>
            {job.description ? (
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                {job.description}
              </p>
            ) : (
              <p className="mt-3 text-sm text-slate-500">
                该来源未提供职位描述；系统不会自行补全 JD 内容。
              </p>
            )}

            {job.requirements.length > 0 ? (
              <>
                <h3 className="mt-6 text-sm font-semibold text-slate-900">来源标注的要求</h3>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {job.requirements.map((requirement) => (
                    <li
                      key={requirement}
                      className="rounded-md bg-slate-50 px-2 py-1 text-xs text-slate-600 ring-1 ring-slate-200 ring-inset"
                    >
                      {requirement}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}

            {job.skills.length > 0 ? (
              <>
                <h3 className="mt-6 text-sm font-semibold text-slate-900">来源标注的技能</h3>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {job.skills.map((skill) => (
                    <li
                      key={skill}
                      className="rounded-md bg-sky-50 px-2 py-1 text-xs text-sky-700 ring-1 ring-sky-200 ring-inset"
                    >
                      {skill}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </section>

          <JobMatchPanel jobId={job.id} />
        </div>

        <aside className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">操作</h2>
            <div className="mt-4">
              <JobActions jobId={job.id} saved={isSaved} />
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">来源与时间</h2>
            <dl className="mt-3">
              <MetaRow label="来源类型" value={formatSourceType(job.source_type)} />
              <MetaRow label="来源标识" value={job.source_key} />
              <MetaRow label="核验状态" value={formatVerificationStatus(job.verification_status)} />
              <MetaRow label="招聘项目" value={job.recruitment_program ?? "未提供"} />
              <MetaRow label="所属部门" value={job.department ?? "未提供"} />
              <MetaRow
                label="发布时间"
                value={job.published_at ? formatDateTime(job.published_at) : "未知"}
              />
              <MetaRow label="首次发现" value={formatDateTime(job.first_seen_at)} />
              <MetaRow
                label="最近核验"
                value={job.last_checked_at ? formatDateTime(job.last_checked_at) : "未知"}
              />
            </dl>

            <a
              href={job.source_url}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-700"
            >
              前往原始页面
              <ArrowUpRight className="size-4" aria-hidden />
            </a>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
              将打开来源网站；请自行确认岗位有效性与投递要求。
            </p>
          </section>

          {job.evidence.length > 0 ? (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">来源证据</h2>
              <ul className="mt-3 space-y-2 text-xs text-slate-600">
                {job.evidence.map((item) => (
                  <li key={item.id} className="rounded-lg bg-slate-50 p-2.5">
                    <p className="font-medium text-slate-800">{item.evidence_kind}</p>
                    <p className="mt-0.5 break-all text-slate-500">{item.source_url}</p>
                    <p className="mt-0.5 text-slate-400">
                      {item.verification_method} · {formatDateTime(item.captured_at)}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
