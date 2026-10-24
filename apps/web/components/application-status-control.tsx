"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { updateApplicationStatus } from "@/lib/client-api";
import { APPLICATION_STATUS_OPTIONS, formatApplicationStatus } from "@/lib/job-display";

export function ApplicationStatusControl({
  applicationId,
  currentStatus,
  onChanged,
}: {
  applicationId: string;
  currentStatus: string;
  /** Lets the detail page reload its header and timeline after a save. */
  onChanged?: () => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState(currentStatus);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleChange(nextStatus: string) {
    const previous = value;
    setValue(nextStatus);
    setPending(true);
    setError(null);

    const result = await updateApplicationStatus(applicationId, nextStatus);
    if (!result.ok) {
      setValue(previous);
      setError(result.error.message);
    } else if (onChanged) {
      // The select alone is not the source of truth: the header text and the
      // timeline would otherwise keep showing the old status.
      onChanged();
    } else {
      router.refresh();
    }
    setPending(false);
  }

  return (
    <div>
      <label htmlFor={`status-${applicationId}`} className="sr-only">
        投递状态
      </label>
      <select
        id={`status-${applicationId}`}
        value={value}
        disabled={pending}
        onChange={(event) => handleChange(event.target.value)}
        className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-800 outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60"
      >
        {APPLICATION_STATUS_OPTIONS.map((status) => (
          <option key={status} value={status}>
            {formatApplicationStatus(status)}
          </option>
        ))}
      </select>
      {pending ? <span className="ml-2 text-[11px] text-slate-400">保存中…</span> : null}
      {error ? <p className="mt-1 text-[11px] text-rose-600">{error}</p> : null}
    </div>
  );
}
