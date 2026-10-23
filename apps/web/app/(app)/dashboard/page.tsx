"use client";

import Link from "next/link";
import { ArrowUpRight, CalendarClock, ClipboardList, Star } from "lucide-react";
import { useEffect, useState } from "react";

import { getDashboardSummary } from "@/lib/client-api";
import type { DashboardSummary } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const COUNT_LABELS: { key: keyof DashboardSummary["counts"]; label: string; href: string }[] = [
  { key: "saved", label: "已收藏岗位", href: "/saved-jobs" },
  { key: "planned", label: "计划申请", href: "/applications" },
  { key: "applied", label: "已申请", href: "/applications" },
  { key: "screening", label: "筛选中", href: "/applications" },
  { key: "assessment", label: "笔试/测评", href: "/applications" },
  { key: "interview", label: "面试中", href: "/applications" },
  { key: "offer", label: "Offer", href: "/applications" },
  { key: "needs_review", label: "待确认", href: "/applications" },
];

const STATUS_LABELS: Record<string, string> = {
  planned: "计划申请",
  to_apply: "待申请",
  applied: "已申请",
  screening: "筛选中",
  assessment: "笔试/测评",
  online_assessment: "在线测评",
  interview: "面试中",
  offer: "Offer",
  rejected: "未通过",
  withdrawn: "已撤回",
  unknown: "状态未知",
};

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getDashboardSummary().then((result) => {
      if (result.ok) setSummary(result.data);
      else setError(result.error.message);
    });
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        工作台数据加载失败：{error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">求职工作台</h1>
        <p className="mt-2 text-sm text-slate-600">
          统计与进度均来自你的真实数据；收藏与计划申请不计入“已申请”。
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {COUNT_LABELS.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-slate-300"
          >
            <p className="text-xs text-slate-500">{item.label}</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
              {summary ? summary.counts[item.key] : "—"}
            </p>
          </Link>
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">最新招聘信息</h2>
            <Link href="/discover" className="text-xs text-sky-700 hover:underline">
              去搜索
            </Link>
          </div>
          <ul className="mt-3 divide-y divide-slate-100">
            {summary?.latest_jobs.length ? (
              summary.latest_jobs.map((job) => (
                <li key={job.id} className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-slate-800">
                        {job.company} · {job.title}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {job.city ?? "城市未知"} · {job.job_type ?? "类型未知"} ·{" "}
                        {job.published_at
                          ? `官网发布 ${formatDateTime(job.published_at)}`
                          : "官网发布日期未知"}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        首次发现 {formatDateTime(job.first_seen_at)}
                        {job.verification_status === "verified"
                          ? " · 已核验完整 JD"
                          : " · 待核验（仅搜索摘要）"}
                      </p>
                    </div>
                    <a
                      href={job.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="shrink-0 text-slate-400 hover:text-sky-700"
                      aria-label="打开官方招聘页"
                    >
                      <ArrowUpRight className="size-4" aria-hidden />
                    </a>
                  </div>
                </li>
              ))
            ) : (
              <li className="py-6 text-center text-sm text-slate-500">暂无近期岗位</li>
            )}
          </ul>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">当前申请进度</h2>
            <Link href="/applications" className="text-xs text-sky-700 hover:underline">
              全部进度
            </Link>
          </div>
          <ul className="mt-3 divide-y divide-slate-100">
            {summary?.recent_events.length ? (
              summary.recent_events.map((event) => (
                <li key={event.id} className="py-3">
                  <p className="text-sm font-medium text-slate-800">
                    {event.company} · {event.title}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {STATUS_LABELS[event.status] ?? event.status} ·{" "}
                    {event.source_type === "email_import"
                      ? "邮件佐证"
                      : event.source_type === "official_api"
                        ? "官方接口"
                        : "用户手动记录"}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    {event.event_time ? formatDateTime(event.event_time) : "时间未知"}
                  </p>
                </li>
              ))
            ) : (
              <li className="py-6 text-center text-sm text-slate-500">暂无申请进度</li>
            )}
          </ul>
        </section>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <CalendarClock className="size-4 text-slate-400" aria-hidden />
          <h2 className="text-sm font-semibold text-slate-900">即将开始</h2>
        </div>
        <ul className="mt-3 divide-y divide-slate-100">
          {summary?.upcoming_events.length ? (
            summary.upcoming_events.map((event) => (
              <li key={`${event.application_id}-${event.starts_at}`} className="py-3">
                <Link
                  href={`/applications/${event.application_id}`}
                  className="flex items-center justify-between gap-3 text-sm text-slate-800 hover:text-sky-700"
                >
                  <span>
                    {event.company} · {event.title} ·{" "}
                    {STATUS_LABELS[event.status] ?? event.status}
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(event.starts_at)}</span>
                </Link>
              </li>
            ))
          ) : (
            <li className="py-6 text-center text-sm text-slate-500">
              暂无已确认的笔试/面试时间（不会根据邮件发送时间自动生成日程）
            </li>
          )}
        </ul>
      </section>

      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        <Link href="/discover" className="inline-flex items-center gap-1 hover:text-sky-700">
          <ClipboardList className="size-3.5" aria-hidden /> 搜索岗位
        </Link>
        <Link href="/saved-jobs" className="inline-flex items-center gap-1 hover:text-sky-700">
          <Star className="size-3.5" aria-hidden /> 我的收藏
        </Link>
      </div>
    </div>
  );
}
