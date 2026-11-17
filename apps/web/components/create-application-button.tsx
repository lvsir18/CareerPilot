"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createApplicationRecord } from "@/lib/client-api";

export function CreateApplicationButton({
  jobId,
  leadId,
  label = "登记申请",
}: {
  jobId?: string;
  leadId?: string;
  label?: string;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleCreate() {
    setPending(true);
    setMessage(null);
    const result = await createApplicationRecord({
      ...(jobId ? { job_id: jobId } : {}),
      ...(leadId ? { job_lead_id: leadId } : {}),
      status: "planned",
    });
    if (!result.ok) {
      setMessage(
        result.error.code === "APPLICATION_EXISTS"
          ? "已有申请记录，无需重复创建。"
          : result.error.message,
      );
    } else {
      setMessage("已创建申请记录，可在投递看板更新状态。");
      router.refresh();
    }
    setPending(false);
  }

  return (
    <div className="text-right">
      <button
        type="button"
        onClick={handleCreate}
        disabled={pending}
        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900 disabled:opacity-60"
      >
        {pending ? "保存中…" : label}
      </button>
      {message ? <p className="mt-1 text-[11px] text-slate-500">{message}</p> : null}
    </div>
  );
}
