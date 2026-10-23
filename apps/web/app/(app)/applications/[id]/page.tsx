"use client";

import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { use, useEffect, useState } from "react";

import { ApplicationStatusControl } from "@/components/application-status-control";
import { ApplicationTimeline } from "@/components/application-timeline";
import { fetchApplicationDetail } from "@/lib/client-api";
import type { ApplicationDetail } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { formatApplicationStatus } from "@/lib/job-display";

export default function ApplicationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const result = await fetchApplicationDetail(id);
    if (result.ok) setDetail(result.data);
    else setError(result.error.message);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) {
    return <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</p>;
  }
  if (!detail) {
    return <p className="text-sm text-slate-500">加载中...</p>;
  }

  const company = detail.job?.company ?? detail.external_company ?? "未知企业";
  const title = detail.job?.title ?? detail.external_title ?? "未知岗位";
  const url = detail.job?.source_url ?? detail.external_url;

  return (
    <div className="space-y-6">
      <Link href="/applications" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800">
        <ArrowLeft className="size-3.5" aria-hidden /> 返回招聘进度
      </Link>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">
              {company} · {title}
            </h1>
            <p className="mt-1 text-xs text-slate-500">
              当前状态：{formatApplicationStatus(detail.status)} · 最近确认：
              {detail.last_confirmed_at ? formatDateTime(detail.last_confirmed_at) : "未确认"}
            </p>
          </div>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-sm text-sky-700 hover:underline"
            >
              查看官网 <ArrowUpRight className="size-3.5" aria-hidden />
            </a>
          ) : null}
        </div>
        <div className="mt-4">
          <ApplicationStatusControl applicationId={detail.id} currentStatus={detail.status} />
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">状态时间线</h2>
        <p className="mt-1 text-xs text-slate-500">来自真实 ApplicationEvent；纠错不覆盖历史。</p>
        <div className="mt-4">
          <ApplicationTimeline applicationId={detail.id} />
        </div>
      </section>

      {detail.notes ? (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">备注</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{detail.notes}</p>
        </section>
      ) : null}
    </div>
  );
}
