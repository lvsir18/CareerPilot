"use client";

import { useRouter } from "next/navigation";
import { StarOff } from "lucide-react";
import { useState } from "react";

import { unsaveJob } from "@/lib/client-api";

export function UnsaveJobButton({
  jobId,
  listType = "saved",
}: {
  jobId: string;
  listType?: "saved" | "to_apply";
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setError(null);
    const result = await unsaveJob(jobId, listType);
    setPending(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <span className="inline-flex flex-col items-end">
      <button
        type="button"
        onClick={handleClick}
        disabled={pending}
        className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-rose-600 disabled:opacity-50"
      >
        <StarOff className="size-3" aria-hidden />
        {pending ? "取消中…" : "取消收藏"}
      </button>
      {error ? <span className="mt-1 text-[11px] text-rose-600">{error}</span> : null}
    </span>
  );
}
