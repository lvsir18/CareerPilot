"use client";

import { CalendarPlus, CalendarSync } from "lucide-react";
import { useState } from "react";

import { addApplicationEvent } from "@/lib/client-api";
import type { ApplicationEvent } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const KINDS = [
  { value: "interview", label: "面试" },
  { value: "assessment", label: "笔试" },
  { value: "online_assessment", label: "在线测评" },
];

/**
 * Manual appointment entry.
 *
 * "改期" and "新增" are different operations: rescheduling must retire the old
 * slot, otherwise the calendar shows the same interview twice. Two real rounds
 * stay possible by using "新增".
 */
export function AppointmentForm({
  applicationId,
  appointments = [],
  onSaved,
}: {
  applicationId: string;
  appointments?: ApplicationEvent[];
  onSaved?: () => void;
}) {
  const [kind, setKind] = useState("interview");
  const [startsAt, setStartsAt] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"new" | "reschedule">(
    appointments.length ? "reschedule" : "new",
  );
  const [targetId, setTargetId] = useState("");
  const candidates = appointments.filter((event) => event.to_status === kind);
  const target = candidates.find((event) => event.id === targetId)
    ?? (candidates.length === 1 ? candidates[0] : undefined);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === "reschedule" && !target) {
      setError("请选择要改期的具体预约，其他轮次将保留");
      return;
    }
    if (!startsAt) {
      setError("请先选择预约的日期和时间");
      return;
    }
    const when = new Date(startsAt);
    if (Number.isNaN(when.getTime())) {
      setError("时间格式无法识别，请重新选择");
      return;
    }
    setPending(true);
    setError(null);
    setSaved(null);
    const result = await addApplicationEvent(applicationId, {
      status: kind,
      // ``datetime-local`` is wall clock in the user's zone; the API stores UTC.
      event_time: when.toISOString(),
      note: note.trim() || undefined,
      evidence_summary: "用户手工登记预约",
      reschedule_event_id: mode === "reschedule" ? target?.id : undefined,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    const label = when.toLocaleString("zh-CN", { hour12: false });
    setSaved(
      mode === "reschedule" ? `已改期到 ${label}，原预约不再占用日历` : `已登记 ${label} 的预约`,
    );
    setStartsAt("");
    setNote("");
    onSaved?.();
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-3">
      <fieldset className="flex flex-wrap gap-3 text-xs">
        <legend className="sr-only">预约方式</legend>
        <label className="inline-flex items-center gap-1.5">
          <input
            type="radio"
            name={`mode-${applicationId}`}
            checked={mode === "new"}
            onChange={() => setMode("new")}
            className="size-3.5"
          />
          新增一轮预约
        </label>
        <label className="inline-flex items-center gap-1.5">
          <input
            type="radio"
            name={`mode-${applicationId}`}
            checked={mode === "reschedule"}
            onChange={() => setMode("reschedule")}
            className="size-3.5"
          />
          改期（仅替换选中的预约）
        </label>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs font-medium text-slate-600">类型</span>
          <select
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setTargetId("");
            }}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {KINDS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-medium text-slate-600">发生时间</span>
          <input
            type="datetime-local"
            value={startsAt}
            onChange={(event) => setStartsAt(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
      </div>
      {mode === "reschedule" ? (
        <div>
          <label
            htmlFor={`reschedule-${applicationId}`}
            className="block text-xs font-medium text-slate-600"
          >
            要改期的预约
          </label>
          <select
            id={`reschedule-${applicationId}`}
            value={target?.id ?? ""}
            onChange={(event) => setTargetId(event.target.value)}
            required
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">请选择具体预约</option>
            {candidates.map((event) => (
              <option key={event.id} value={event.id}>
                {formatDateTime(event.event_time)}{event.note ? ` · ${event.note}` : ""}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">
            只替换选中的这一条，其他面试或笔试预约继续保留。
          </p>
        </div>
      ) : null}
      <label className="block">
        <span className="text-xs font-medium text-slate-600">备注（可选）</span>
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="例如：HR 电话约定一面，线上会议链接稍后发送"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
      <button
        type="submit"
        disabled={pending}
        className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {mode === "reschedule" ? (
          <CalendarSync className="size-4" aria-hidden />
        ) : (
          <CalendarPlus className="size-4" aria-hidden />
        )}
        {pending ? "保存中…" : mode === "reschedule" ? "保存改期" : "保存预约"}
      </button>
      {error ? <p className="break-words text-xs text-rose-600">{error}</p> : null}
      {saved ? <p className="break-words text-xs text-emerald-700">{saved}</p> : null}
      <p className="text-[11px] leading-relaxed text-slate-500">
        「改期」只替换选中的预约，历史记录仍保留在时间线里；如果确实有两轮面试，请用「新增」。
        预约时间与「最近确认」是两件事：确认时间记录你登记这一刻，日历显示的是预约本身。
      </p>
    </form>
  );
}
