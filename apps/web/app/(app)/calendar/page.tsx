"use client";

import Link from "next/link";
import { CalendarClock, CalendarPlus, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getCalendarEvents } from "@/lib/client-api";
import type { DashboardCalendarEvent } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const STATUS_LABELS: Record<string, string> = {
  assessment: "笔试/测评",
  online_assessment: "在线测评",
  interview: "面试",
};

type View = "month" | "week" | "list";

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

/** One row per appointment: the same slot must never be listed twice. */
function dedupe(items: DashboardCalendarEvent[]): DashboardCalendarEvent[] {
  const seen = new Set<string>();
  const result: DashboardCalendarEvent[] = [];
  for (const item of items) {
    const identity = `${item.application_id}|${new Date(item.starts_at).toISOString()}`;
    if (seen.has(identity)) continue;
    seen.add(identity);
    result.push(item);
  }
  return result;
}

export default function CalendarPage() {
  const [events, setEvents] = useState<DashboardCalendarEvent[]>([]);
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading");
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [view, setView] = useState<View>("month");
  const [cursor, setCursor] = useState(() => new Date());
  // "Now" is captured when data arrives so render stays pure.
  const [now, setNow] = useState(0);

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

  const visibleCells = view === "week" ? weekCells : monthCells;
  const rangeStart = useMemo(() => {
    const first = visibleCells[0];
    if (!first) return new Date().toISOString();
    return new Date(first.getFullYear(), first.getMonth(), first.getDate()).toISOString();
  }, [visibleCells]);
  const rangeEnd = useMemo(() => {
    const last = visibleCells[visibleCells.length - 1];
    if (!last) return new Date().toISOString();
    return new Date(last.getFullYear(), last.getMonth(), last.getDate() + 1).toISOString();
  }, [visibleCells]);

  useEffect(() => {
    let active = true;
    void (async () => {
      setStatus("loading");
      const result = await getCalendarEvents(rangeStart, rangeEnd);
      if (!active) return;
      if (!result.ok) {
        setError(result.error.message);
        setStatus("error");
        return;
      }
      setError(null);
      setEvents(dedupe(result.data.events));
      setNow(Date.now());
      setStatus("ready");
    })();
    return () => {
      active = false;
    };
  }, [rangeStart, rangeEnd, reloadKey]);

  function shift(step: number) {
    const next = new Date(cursor);
    if (view === "week") next.setDate(next.getDate() + step * 7);
    else next.setMonth(next.getMonth() + step);
    setCursor(next);
  }

  function eventsOn(day: Date): DashboardCalendarEvent[] {
    return events.filter((event) => sameDay(new Date(event.starts_at), day));
  }

  const upcoming = useMemo(
    () =>
      events
        .filter((event) => new Date(event.starts_at).getTime() >= now)
        .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()),
    [events, now],
  );
  const history = useMemo(
    () =>
      events
        .filter((event) => new Date(event.starts_at).getTime() < now)
        .sort((a, b) => new Date(b.starts_at).getTime() - new Date(a.starts_at).getTime()),
    [events, now],
  );

  const title =
    view === "week"
      ? `${startOfWeek(cursor).toLocaleDateString()} - ${new Date(
          startOfWeek(cursor).getTime() + 6 * 86400000,
        ).toLocaleDateString()}`
      : `${cursor.getFullYear()} 年 ${cursor.getMonth() + 1} 月`;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">面试日程</h1>
          <p className="mt-2 text-sm text-slate-600">
            这里只显示已明确的笔试/面试预约时间。投递、初筛等状态变更请到申请的进度时间线查看。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/applications"
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-slate-400"
          >
            <CalendarPlus className="size-3.5" aria-hidden />
            登记预约
          </Link>
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
        </div>
      </section>

      {status === "error" ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4">
          <p className="break-words text-sm text-rose-700">
            {error ?? "日程读取失败，请稍后重试。"}
          </p>
          <button
            type="button"
            onClick={() => setReloadKey((prev) => prev + 1)}
            className="mt-2 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
          >
            <RefreshCw className="size-3" aria-hidden />
            重新加载
          </button>
        </div>
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

          {status === "loading" ? (
            <p className="mt-3 text-xs text-slate-500">正在加载日程…</p>
          ) : null}

          <div className="mt-3 grid grid-cols-7 gap-1 text-center text-[11px] text-slate-400">
            {["一", "二", "三", "四", "五", "六", "日"].map((day) => (
              <div key={day}>{day}</div>
            ))}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1">
            {visibleCells.map((day, index) => {
              const dayEvents = eventsOn(day);
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
                    {dayEvents.slice(0, 2).map((event) => (
                      <Link
                        key={event.id}
                        href={`/applications/${event.application_id}`}
                        className="block truncate rounded bg-sky-50 px-1 py-0.5 text-[10px] text-sky-700"
                        title={`${event.company} · ${event.title}`}
                      >
                        {event.company} {STATUS_LABELS[event.status] ?? "日程"}
                      </Link>
                    ))}
                    {dayEvents.length > 2 ? (
                      <span className="text-[10px] text-slate-400">+{dayEvents.length - 2}</span>
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
              <li key={event.id} className="py-3">
                <Link
                  href={`/applications/${event.application_id}`}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-800 hover:text-sky-700"
                >
                  <span className="min-w-0 break-words">
                    {event.company} · {event.title} · {STATUS_LABELS[event.status] ?? "日程"}
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(event.starts_at)}</span>
                </Link>
              </li>
            ))
          ) : (
            <li className="py-6 text-center text-sm text-slate-500">
              暂无已确认的笔试/面试时间。可以在
              <Link href="/applications" className="mx-1 text-sky-700 hover:underline">
                投递看板
              </Link>
              打开某条申请后手工登记。
            </li>
          )}
        </ul>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">历史日程</h2>
        <ul className="mt-3 divide-y divide-slate-100">
          {history.length ? (
            history.map((event) => (
              <li key={event.id} className="py-3">
                <Link
                  href={`/applications/${event.application_id}`}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-700 hover:text-sky-700"
                >
                  <span className="min-w-0 break-words">
                    {event.company} · {event.title} · {STATUS_LABELS[event.status] ?? "日程"}
                  </span>
                  <span className="text-xs text-slate-500">{formatDateTime(event.starts_at)}</span>
                </Link>
              </li>
            ))
          ) : (
            <li className="py-6 text-center text-sm text-slate-500">所选范围内没有历史日程</li>
          )}
        </ul>
      </section>
    </div>
  );
}