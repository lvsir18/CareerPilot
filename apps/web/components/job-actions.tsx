"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { BookmarkPlus, ClipboardList, StarOff } from "lucide-react";

import { saveJob, unsaveJob } from "@/lib/client-api";

type PendingAction = "saved" | "to_apply" | "unsave" | null;

export function JobActions({ jobId, saved }: { jobId: string; saved: boolean }) {
  const router = useRouter();
  const [pending, setPending] = useState<PendingAction>(null);
  const [isSaved, setIsSaved] = useState(saved);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSave(listType: "saved" | "to_apply") {
    setPending(listType);
    setError(null);
    setMessage(null);

    const result = await saveJob(jobId, listType);
    if (!result.ok) {
      setError(result.error.message);
    } else {
      if (listType === "saved") setIsSaved(true);
      setMessage(
        listType === "saved"
          ? "已加入收藏（重复操作不会产生重复记录）。"
          : "已加入待投递清单，可在投递看板中记录进度。",
      );
      router.refresh();
    }
    setPending(null);
  }

  async function handleUnsave() {
    setPending("unsave");
    setError(null);
    setMessage(null);
    const result = await unsaveJob(jobId, "saved");
    if (!result.ok) {
      setError(result.error.message);
    } else {
      setIsSaved(false);
      setMessage("已从收藏中移除。");
      router.refresh();
    }
    setPending(null);
  }

  return (
    <div className="space-y-3">
      {isSaved ? (
        <button
          type="button"
          onClick={handleUnsave}
          disabled={pending !== null}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:border-rose-300 hover:text-rose-700 disabled:opacity-60"
        >
          <StarOff className="size-4" aria-hidden />
          {pending === "unsave" ? "处理中…" : "取消收藏"}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => handleSave("saved")}
          disabled={pending !== null}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900 disabled:opacity-60"
        >
          <BookmarkPlus className="size-4" aria-hidden />
          {pending === "saved" ? "处理中…" : "收藏岗位"}
        </button>
      )}
      <button
        type="button"
        onClick={() => handleSave("to_apply")}
        disabled={pending !== null}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:opacity-60"
      >
        <ClipboardList className="size-4" aria-hidden />
        {pending === "to_apply" ? "处理中…" : "加入待投递清单"}
      </button>

      {message ? (
        <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          {message}{" "}
          <Link href="/applications" className="font-medium underline">
            查看投递看板
          </Link>
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {error}
        </p>
      ) : null}
      <p className="text-xs leading-relaxed text-slate-500">
        本操作只写入本系统。CareerPilot
        不会自动打开或提交外部申请，请通过右侧原始链接自行投递。
      </p>
    </div>
  );
}
