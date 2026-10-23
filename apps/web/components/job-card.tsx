import Link from "next/link";
import { ArrowUpRight, MapPin } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import type { JobListItem } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  formatJobFamily,
  formatJobStatus,
  formatJobType,
  formatSourceType,
  formatVerificationStatus,
  jobStatusTone,
  verificationTone,
} from "@/lib/job-display";

export function JobCard({ job }: { job: JobListItem }) {
  return (
    <article className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:border-slate-300 hover:shadow-md">
      <div className="flex flex-wrap items-center gap-2">
        {job.is_demo ? (
          <StatusPill tone="warning">演示数据</StatusPill>
        ) : (
          <StatusPill tone="neutral">真实来源</StatusPill>
        )}
        <span className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-500 ring-1 ring-slate-200 ring-inset">
          {formatSourceType(job.source_type)}
        </span>
        <StatusPill tone={jobStatusTone(job.status)}>{formatJobStatus(job.status)}</StatusPill>
        {!job.is_demo ? (
          <StatusPill tone={verificationTone(job.verification_status)}>
            {formatVerificationStatus(job.verification_status)}
          </StatusPill>
        ) : null}
      </div>

      <h3 className="mt-3 text-base font-semibold leading-snug text-slate-900">
        <Link href={`/jobs/${job.id}`} className="hover:text-sky-700">
          {job.title}
        </Link>
      </h3>
      <p className="mt-1 text-sm text-slate-600">{job.company}</p>
      {job.department || job.recruitment_program ? (
        <p className="mt-1 text-xs text-slate-400">
          {[job.department, job.recruitment_program].filter(Boolean).join(" · ")}
        </p>
      ) : null}

      <dl className="mt-4 space-y-1.5 text-xs text-slate-500">
        <div className="flex items-center gap-1.5">
          <MapPin className="size-3.5 text-slate-400" aria-hidden />
          <dt className="sr-only">城市</dt>
          <dd>{job.city ?? job.location_text ?? "城市未知"}</dd>
          <span className="text-slate-300">·</span>
          <dd>{formatJobType(job.job_type)}</dd>
          <span className="text-slate-300">·</span>
          <dd>{formatJobFamily(job.job_family)}</dd>
        </div>
        <div className="flex items-center gap-1.5">
          <dt>发布时间</dt>
          <dd className={job.published_at ? "text-slate-700" : "text-amber-700"}>
            {job.published_at ? formatDateTime(job.published_at) : "未知（来源未提供）"}
          </dd>
        </div>
        <div className="flex items-center gap-1.5">
          <dt>首次发现</dt>
          <dd>{formatDateTime(job.first_seen_at)}</dd>
        </div>
      </dl>

      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
        <Link
          href={`/jobs/${job.id}`}
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-700 hover:text-slate-900"
        >
          查看 JD
          <ArrowUpRight className="size-3" aria-hidden />
        </Link>
        <a
          href={job.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
        >
          原始来源
          <ArrowUpRight className="size-3" aria-hidden />
        </a>
      </div>
    </article>
  );
}
