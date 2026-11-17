"use client";

import { Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { deleteApplication } from "@/lib/client-api";

export function DeleteApplicationButton({
  applicationId,
  title,
  compact = false,
}: {
  applicationId: string;
  title: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    const confirmed = window.confirm(
      `确定删除这条申请记录？\n\n${title}\n\n删除后该记录的时间线与邮件关联一并移除，且无法恢复。`,
    );
    if (!confirmed) {
      return;
    }
    setPending(true);
    setError(null);
    const result = await deleteApplication(applicationId);
    setPending(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <span className="inline-flex flex-col items-start">
      <button
        type="button"
        onClick={() => void handleDelete()}
        disabled={pending}
        aria-label={`删除申请记录：${title}`}
        title="删除申请记录"
        className={
          compact
            ? "rounded p-1 text-slate-400 transition-colors hover:text-rose-600 disabled:opacity-40"
            : "inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-600 transition-colors hover:border-rose-300 hover:text-rose-700 disabled:opacity-50"
        }
      >
        <Trash2 className={compact ? "size-3" : "size-3.5"} aria-hidden />
        {compact ? null : pending ? "删除中…" : "删除"}
      </button>
      {error ? <span className="mt-1 text-[11px] text-rose-600">{error}</span> : null}
    </span>
  );
}