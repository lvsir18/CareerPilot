"use client";

import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { use, useCallback, useEffect, useState } from "react";

import { ApplicationStatusControl } from "@/components/application-status-control";
import { ApplicationTimeline } from "@/components/application-timeline";
import { AppointmentForm } from "@/components/appointment-form";
import { cancelApplicationEvent, fetchApplicationDetail } from "@/lib/client-api";
import type { ApplicationDetail } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { formatApplicationStatus } from "@/lib/job-display";

export default function ApplicationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  // Bumped after a save so the open timeline reloads instead of going stale.
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(async () => {
    const result = await fetchApplicationDetail(id);
    if (result.ok) {
      setDetail(result.data);
      setError(null);
    } else {
      setError(result.error.message);
    }
  }, [id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void refresh();
  }, [refresh]);

  function afterChange() {
    void refresh();
    setRefreshKey((key) => key + 1);
  }

  async function cancelAppointment(eventId: string) {
    if (!detail) return;
    setCancelling(eventId);
    setError(null);
    const result = await cancelApplicationEvent(detail.id, eventId);
    setCancelling(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    afterChange();
  }

  if (error && !detail) {
    return (
      <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</p>
    );
  }
  if (!detail) {
    return <p className="text-sm text-slate-500">加载中...</p>;
  }

  // Active slots only: a rescheduled or cancelled appointment stays in the
  // timeline as history but must not appear as a live appointment here.
  const activeAppointments = detail.events.filter(
    (event) => event.is_scheduled && !event.superseded_at,
  );
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
          <div className="min-w-0">
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
          <ApplicationStatusControl
            applicationId={detail.id}
            currentStatus={detail.status}
            onChanged={afterChange}
          />
        </div>
        {error ? <p className="mt-2 break-words text-xs text-rose-600">{error}</p> : null}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">登记笔试 / 面试预约</h2>
        <p className="mt-1 text-xs text-slate-500">
          手工填入发生时间后，会立即出现在「面试日程」里；改期请用表单里的「改期」选项，
          旧预约会被替代而不是继续占位。
        </p>
        {activeAppointments.length ? (
          <ul className="mt-3 space-y-2">
            {activeAppointments.map((event) => (
              <li
                key={event.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
              >
                <span className="text-slate-700">
                  当前预约：{formatDateTime(event.event_time)} · {formatApplicationStatus(event.to_status)}
                  {event.evidence_summary ? ` · ${event.evidence_summary}` : ""}
                </span>
                <button
                  type="button"
                  onClick={() => void cancelAppointment(event.id)}
                  disabled={cancelling === event.id}
                  className="text-rose-600 hover:underline disabled:opacity-50"
                >
                  {cancelling === event.id ? "取消中…" : "取消这条预约"}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-xs text-slate-500">目前没有生效中的预约。</p>
        )}
        <AppointmentForm
          applicationId={detail.id}
          appointments={activeAppointments}
          onSaved={afterChange}
        />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">状态时间线</h2>
        <p className="mt-1 text-xs text-slate-500">来自真实 ApplicationEvent；纠错不覆盖历史。</p>
        <div className="mt-4">
          <ApplicationTimeline applicationId={detail.id} refreshKey={refreshKey} />
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
