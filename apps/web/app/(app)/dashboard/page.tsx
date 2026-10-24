"use client";

import Link from "next/link";
import { ArrowUpRight, CalendarClock, ClipboardList, Star } from "lucide-react";
import { useEffect, useState } from "react";

import { getDashboardSummary } from "@/lib/client-api";
import type { DashboardSummary } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  formatApplicationSource,
  formatApplicationStatus,
  formatJobType,
  formatVerificationStatus,
} from "@/lib/job-display";

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



export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getDashboardSummary().then((result) => {
      if (result.ok) setSummary(result.data);
      else setError(result.error.message);
    });
  }, []);

  // A brand-new account sees an empty board; the three steps above are what a
  // first-time user actually needs, so they replace the bare "0 / 0 / 0" grid.
  const isNewcomer =
    summary !== null &&
    summary.counts.saved === 0 &&
    summary.counts.planned === 0 &&
    summary.counts.applied === 0 &&
    summary.counts.interview === 0 &&
    summary.counts.offer === 0;

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

      {isNewcomer ? (
        <section className="rounded-xl border border-sky-200 bg-sky-50 p-5">
          <h2 className="text-sm font-semibold text-sky-900">从这里开始（约 5 分钟）</h2>
          <ol className="mt-3 grid gap-3 text-xs leading-relaxed text-sky-900 sm:grid-cols-3">
            <li className="rounded-lg bg-white/70 p-3">
              <p className="font-medium">1. 上传简历</p>
              <p className="mt-1 text-sky-800">PDF / DOCX，失败会明确告诉你原因。</p>
              <Link href="/resumes" className="mt-2 inline-block font-medium underline">
                去上传
              </Link>
            </li>
            <li className="rounded-lg bg-white/70 p-3">
              <p className="font-medium">2. 核对并确认画像</p>
              <p className="mt-1 text-sky-800">确认后才会参与岗位匹配。</p>
              <Link href="/profile" className="mt-2 inline-block font-medium underline">
                去核对
              </Link>
            </li>
            <li className="rounded-lg bg-white/70 p-3">
              <p className="font-medium">3. 查看推荐 / 发现岗位</p>
              <p className="mt-1 text-sky-800">收藏或加入待投递，再登记真实进度。</p>
              <Link href="/matches" className="mt-2 inline-block font-medium underline">
                看推荐
              </Link>
            </li>
          </ol>
        </section>
      ) : null}

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
                        {job.city ?? "城市未知"} · {formatJobType(job.job_type)} ·{" "}
                        {job.published_at
                          ? `官网发布 ${formatDateTime(job.published_at)}`
                          : "官网发布日期未知"}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        首次发现 {formatDateTime(job.first_seen_at)} ·{" "}
                        {formatVerificationStatus(job.verification_status)}
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
                    {formatApplicationStatus(event.status)} ·{" "}
                    {formatApplicationSource(event.source_type)}
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
                    {formatApplicationStatus(event.status)}
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
