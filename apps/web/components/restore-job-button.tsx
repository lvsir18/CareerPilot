"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { restoreArchivedJob } from "@/lib/client-api";

/** Admin-only: un-archive a posting. It does not claim the role is open again. */
export function RestoreJobButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function restore() {
    setBusy(true);
    setError(null);
    const result = await restoreArchivedJob(jobId);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <span className="text-xs text-slate-500">已归档：不参与检索与推荐</span>
      <button
        type="button"
        onClick={() => void restore()}
        disabled={busy}
        className="text-xs font-medium text-sky-700 hover:underline disabled:opacity-40"
      >
        {busy ? "恢复中…" : "恢复"}
      </button>
      {error ? <span className="text-xs text-rose-700">{error}</span> : null}
    </div>
  );
}
