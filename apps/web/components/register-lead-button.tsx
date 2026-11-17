"use client";

import { ClipboardList } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createApplicationRecord } from "@/lib/client-api";

/**
 * Turns a saved private JD into a board entry with one click. Jumping to an
 * empty /applications page forced the user to re-enter what they just imported.
 */
export function RegisterLeadButton({
  leadId,
  company,
  title,
}: {
  leadId: string;
  company: string;
  title: string;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setError(null);
    const result = await createApplicationRecord({
      job_lead_id: leadId,
      status: "planned",
      notes: `来自私有 JD：${company} · ${title}`,
    });
    if (!result.ok) {
      const existing = result.error.details?.application_id;
      if (result.error.code === "APPLICATION_EXISTS" && typeof existing === "string") {
        // Already registered: go straight to the existing record instead of
        // making the user hunt for it.
        router.push(`/applications/${existing}`);
        return;
      }
      setPending(false);
      setError(result.error.message);
      return;
    }
    router.push(`/applications/${result.data.id}`);
  }

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={handleClick}
        disabled={pending}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:border-slate-400 disabled:opacity-40"
      >
        <ClipboardList className="size-4" aria-hidden />
        {pending ? "登记中…" : "登记到投递看板"}
      </button>
      <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
        自动带入这个候选岗位的企业、岗位名和来源链接，登记后可在详情里补充状态与预约。
      </p>
      {error ? <p className="mt-1 break-words text-[11px] text-rose-600">{error}</p> : null}
    </div>
  );
}
