"use client";

import { useEffect, useRef, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { fetchApplicationDetail } from "@/lib/client-api";
import type { ApplicationEvent } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  formatApplicationSource,
  formatApplicationStatus,
  formatEventVerification,
} from "@/lib/job-display";

export function ApplicationTimeline({
  applicationId,
  refreshKey,
}: {
  applicationId: string;
  /** Bump this after a status/appointment change to reload an open timeline. */
  refreshKey?: number;
}) {
  const [events, setEvents] = useState<ApplicationEvent[] | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const appliedKey = useRef(refreshKey);

  async function load() {
    setPending(true);
    setError(null);
    const result = await fetchApplicationDetail(applicationId);
    setPending(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setEvents(result.data.events);
  }

  useEffect(() => {
    if (refreshKey === undefined || refreshKey === appliedKey.current) {
      return;
    }
    appliedKey.current = refreshKey;
    // Only an already-open timeline refreshes itself; before that the user has
    // not asked to load it yet.
    if (events !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only on key change
  }, [refreshKey, events]);

  if (events === null) {
    return (
      <div>
        <button
          type="button"
          onClick={load}
          disabled={pending}
          className="text-xs font-medium text-sky-700 hover:underline disabled:opacity-50"
        >
          {pending ? "加载时间线..." : "查看状态时间线"}
        </button>
        {error ? <p className="mt-1 text-xs text-rose-600">{error}</p> : null}
      </div>
    );
  }

  return (
    <ol className="mt-3 space-y-2 border-l border-slate-200 pl-3">
      {events.map((event) => (
        <li key={event.id} className="relative text-xs">
          <span className="absolute -left-[17px] top-1 size-2 rounded-full bg-slate-300" />
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-slate-800">
              {formatApplicationStatus(event.new_status)}
            </span>
            <StatusPill tone={event.verification_status === "email_confirmed" ? "ok" : "info"}>
              {formatEventVerification(event.verification_status)}
            </StatusPill>
            <span className="text-slate-400">{formatDateTime(event.event_time)}</span>
            {event.superseded_at ? (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                已被改期/取消
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-slate-500">
            来源：{formatApplicationSource(event.source_type)}
            {event.evidence_summary ? ` · ${event.evidence_summary}` : ""}
          </p>
          {event.note ? <p className="mt-0.5 text-slate-400">{event.note}</p> : null}
        </li>
      ))}
      {pending ? <li className="text-[11px] text-slate-400">正在刷新…</li> : null}
      {error ? <li className="text-[11px] text-rose-600">{error}</li> : null}
    </ol>
  );
}
