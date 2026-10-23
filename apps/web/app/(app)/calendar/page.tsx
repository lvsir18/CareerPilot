"use client";

import Link from "next/link";
import { CalendarClock, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getDashboardSummary } from "@/lib/client-api";
import type { DashboardSummary } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const STATUS_LABELS: Record<string, string> = {
  assessment: "笔试/测评",
  online_assessment: "在线测评",
  interview: "面试",
  offer: "Offer",
};

type View = "month" | "week" | "list";
type EventItem = {
  key: string;
  application_id: string;
  company: string;
  title: string;
  status: string;
  starts_at: string;
};

function startOfWeek(date: Date): Date {
  const copy = new Date(date);
  const day = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - day);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export default function CalendarPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("month");
  const [cursor, setCursor] = useState(() => new Date());

  useEffect(() => {
    void getDashboardSummary().then((result) => {
      if (result.ok) setSummary(result.data);
      else setError(result.error.message);
    });
  }, []);

  const upcoming: EventItem[] = useMemo(
    () =>
      (summary?.upcoming_events ?? []).map((event) => ({
        key: `${event.application_id}-${event.starts_at}`,
        application_id: event.application_id,
        company: event.company,
        title: event.title,
        status: event.status,
        starts_at: event.starts_at,
      })),
    [summary],
  );

  const history: EventItem[] = useMemo(
    () =>
      (summary?.recent_events ?? [])
        .filter((event) => event.event_time)
        .map((event) => ({
          key: event.id,
          application_id: event.application_id,
          company: event.company,
          title: event.title,
          status: event.status,
          starts_at: event.event_time as string,
        })),
    [summary],
  );

  const allEvents = useMemo(() => [...upcoming, ...history], [upcoming, history]);

  function shift(step: number) {
    const next = new Date(cursor);
    if (view === "week") next.setDate(next.getDate() + step * 7);
    else next.setMonth(next.getMonth() + step);
    setCursor(next);
  }

  const monthCells = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const start = startOfWeek(first);
    return Array.from({ length: 42 }, (_, index) => {
      const day = new Date(start);
      day.setDate(start.getDate() + index);
      return day;
    });
  }, [cursor]);

  const weekCells = useMemo(() => {
    const start = startOfWeek(cursor);
    return Array.from({ length: 7 }, (_, index) => {
      const day = new Date(start);
      day.setDate(start.getDate() + index);
      return day;
    });
  }, [cursor]);

  function eventsOn(day: Date): EventItem[] {
    return allEvents.filter((event) => sameDay(new Date(event.starts_at), day));
  }

  const title =
    view === "week"
      ? `${startOfWeek(cursor).toLocaleDateString()} - ${new Date(
          startOfWeek(cursor).getTime() + 6 * 86400000,
        ).toLocaleDateString()}`
      : `${cursor.getFullYear()} 年 ${cursor.getMonth() + 1} 月`;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">面试日程</h1>
          <p className="mt-2 text-sm text-slate-600">
            只展示已确认或邮件中明确给出预约时间的笔试/面试；邮件发送时间不会被当作面试开始时间。
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
          {[
            { key: "month", label: "月" },
            { key: "week", label: "周" },
            { key: "list", label: "列表" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setView(item.key as View)}
              aria-pressed={view === item.key}
              className={`rounded-md px-3 py-1 text-xs ${
                view === item.key ? "bg-slate-900 text-white" : "text-slate-600"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      {error ? (
        <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</p>
      ) : null}

      {view !== "list" ? (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => shift(-1)}
              aria-label="上一页"
              className="rounded-lg border border-slate-200 p-1.5 text-slate-600"
            >
              <ChevronLeft className="size-4" aria-hidden />
            </button>
            <span className="text-sm font-medium text-slate-800">{title}</span>
            <button
              type="button"
              onClick={() => shift(1)}
              aria-label="下一页"
              className="rounded-lg border border-slate-200 p-1.5 text-slate-600"
            >
              <ChevronRight className="size-4" aria-hidden />
            </button>
          </div>

          <div className="mt-3 grid grid-cols-7 gap-1 text-center text-[11px] text-slate-400">
            {["一", "二", "三", "四", "五", "六", "日"].map((day) => (
              <div key={day}>{day}</div>
            ))}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1">
            {(view === "week" ? weekCells : monthCells).map((day, index) => {
              const events = eventsOn(day);
              const inMonth = day.getMonth() === cursor.getMonth();
              return (
                <div
                  key={index}
                  className={`min-h-16 rounded-lg border p-1 text-left ${
                    inMonth || view === "week"
                      ? "border-slate-200 bg-white"
                      : "border-slate-100 bg-slate-50/50 text-slate-300"
                  }`}
                >
                  <span className="text-[11px] text-slate-500">{day.getDate()}</span>
                  <div className="mt-1 space-y-0.5">
                    {events.slice(0, 2).map((event) => (
                      <Link
                        key={event.key}
                        href={`/applications/${event.application_id}`}
                        className="block truncate rounded bg-sky-50 px-1 py-0.5 text-[10px] text-sky-700"
                        title={`${event.company} · ${event.title}`}
                      >
                        {event.company} {STATUS_LABELS[event.status] ?? event.status}
                      </Link>
                    ))}
                    {events.length > 2 ? (
                      <span className="text-[10px] text-slate-400">+{events.length - 2}</span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <CalendarClock className="size-4 text-slate-400" aria-hidden />
          <h2 className="text-sm font-semibold text-slate-900">即将开始</h2>
        </div>
        <ul className="mt-3 divide-y divide-slate-100">
          {upcoming.length ? (
            upcoming.map((event) => (
              <li key={event.key} className="py-3">
                <Link
                  href={`/applications/${event.application_id}`}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-800 hover:text-sky-700"
                >
                  <span>
                    {event.company} · {event.title} · {STATUS_LABELS[event.status] ?? event.status}
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(event.starts_at)}</span>
                </Link>
              </li>
            ))
          ) : (
            <li className="py-6 text-center text-sm text-slate-500">暂无已确认的笔试/面试时间</li>
          )}
        </ul>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">历史事件</h2>
        <ul className="mt-3 divide-y divide-slate-100">
          {history.length ? (
            history.map((event) => (
              <li key={event.key} className="py-3">
                <Link
                  href={`/applications/${event.application_id}`}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-700 hover:text-sky-700"
                >
                  <span>
                    {event.company} · {event.title} · {STATUS_LABELS[event.status] ?? event.status}
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(event.starts_at)}</span>
                </Link>
              </li>
            ))
          ) : (
            <li className="py-6 text-center text-sm text-slate-500">暂无历史事件</li>
          )}
        </ul>
      </section>
    </div>
  );
}
