"use client";

import { AlertTriangle, MailCheck, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  confirmRecruitmentCandidate,
  discardRecruitmentCandidate,
  listRecruitmentCandidates,
} from "@/lib/client-api";
import type { ApplicationRecord, RecruitmentCandidate } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  APPLICATION_STATUS_OPTIONS,
  formatApplicationStatus,
} from "@/lib/job-display";

const CONFLICT_LABEL: Record<string, string> = {
  duplicate: "重复事件",
  out_of_order: "时间早于当前状态",
  ambiguous_match: "无法确定对应申请",
  status_conflict: "状态互相矛盾",
  missing_information: "缺少明确阶段",
};

export function EmailSyncCenter({ applications }: { applications: ApplicationRecord[] }) {
  const [candidates, setCandidates] = useState<RecruitmentCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const result = await listRecruitmentCandidates();
    if (result.ok) setCandidates(result.data);
    else setError(result.error.message);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void refresh();
  }, []);

  async function handleConfirm(candidate: RecruitmentCandidate, status: string, applicationId: string, keepCurrent: boolean) {
    setBusy(true);
    setError(null);
    const result = await confirmRecruitmentCandidate(candidate.id, {
      application_id: applicationId || undefined,
      status: status || undefined,
      keep_current: keepCurrent,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    await refresh();
  }

  async function handleDiscard(candidate: RecruitmentCandidate) {
    const result = await discardRecruitmentCandidate(candidate.id);
    if (!result.ok) setError(result.error.message);
    else await refresh();
  }

  const pending = candidates.filter((item) => item.review_status !== "confirmed" && item.review_status !== "discarded");
  if (pending.length === 0 && !error) return null;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-4">
        <MailCheck className="size-4 text-slate-400" aria-hidden />
        <div>
          <h2 className="text-sm font-semibold text-slate-900">邮箱同步待确认</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            来自邮箱的招聘进度建议；确认前不会修改申请状态。
          </p>
        </div>
        <span className="ml-auto text-xs text-slate-500">{pending.length} 条</span>
      </div>

      {error ? <p className="px-5 py-3 text-sm text-rose-700">{error}</p> : null}

      <ul className="divide-y divide-slate-100">
        {pending.map((candidate) => (
          <CandidateRow
            key={candidate.id}
            candidate={candidate}
            applications={applications}
            busy={busy}
            onConfirm={handleConfirm}
            onDiscard={handleDiscard}
          />
        ))}
      </ul>
    </section>
  );
}

function CandidateRow({
  candidate,
  applications,
  busy,
  onConfirm,
  onDiscard,
}: {
  candidate: RecruitmentCandidate;
  applications: ApplicationRecord[];
  busy: boolean;
  onConfirm: (
    candidate: RecruitmentCandidate,
    status: string,
    applicationId: string,
    keepCurrent: boolean,
  ) => Promise<void>;
  onDiscard: (candidate: RecruitmentCandidate) => Promise<void>;
}) {
  const [applicationId, setApplicationId] = useState(candidate.matched_application_id ?? "");
  const [status, setStatus] = useState(candidate.parsed_status ?? "");
  const hasConflict = candidate.conflict_kind !== "none";

  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-slate-900">
          {candidate.parsed_company ?? "未知企业"} · {candidate.parsed_title ?? "未知岗位"}
        </span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
          {candidate.provider === "qq_imap" ? "QQ 邮箱" : "Gmail"}
        </span>
        <span className="text-[11px] text-slate-400">
          置信度 {Math.round(candidate.confidence * 100)}%
        </span>
        {hasConflict ? (
          <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-800 ring-1 ring-amber-200 ring-inset">
            <AlertTriangle className="size-3" aria-hidden />
            {CONFLICT_LABEL[candidate.conflict_kind] ?? candidate.conflict_kind}
          </span>
        ) : null}
      </div>

      <p className="mt-1 text-xs text-slate-500">
        解析状态：{candidate.parsed_status ? formatApplicationStatus(candidate.parsed_status) : "未明确"}
        {" · 事件时间："}
        {candidate.event_time ? formatDateTime(candidate.event_time) : "未知"}
      </p>
      {candidate.conflict_reason ? (
        <p className="mt-1 text-xs text-amber-700">{candidate.conflict_reason}</p>
      ) : null}
      {candidate.evidence_summary ? (
        <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{candidate.evidence_summary}</p>
      ) : null}

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <select
          value={applicationId}
          onChange={(event) => setApplicationId(event.target.value)}
          aria-label="匹配申请"
          className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
        >
          <option value="">选择申请记录</option>
          {applications.map((application) => (
            <option key={application.id} value={application.id}>
              {(application.job?.title ?? application.external_title ?? "未命名")} ·{" "}
              {(application.job?.company ?? application.external_company ?? "未知")}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          aria-label="目标状态"
          className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
        >
          <option value="">使用邮件解析状态</option>
          {APPLICATION_STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {formatApplicationStatus(option)}
            </option>
          ))}
        </select>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy || !applicationId}
            onClick={() => void onConfirm(candidate, status, applicationId, false)}
            className="flex-1 rounded-lg bg-sky-600 px-2 py-1.5 text-xs font-medium text-white disabled:opacity-40"
          >
            确认更新
          </button>
          <button
            type="button"
            disabled={busy || !applicationId}
            onClick={() => void onConfirm(candidate, status, applicationId, true)}
            className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs text-slate-700 disabled:opacity-40"
          >
            仅保留当前
          </button>
          <button
            type="button"
            onClick={() => void onDiscard(candidate)}
            aria-label="忽略"
            className="rounded-lg px-2 py-1.5 text-slate-400"
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </li>
  );
}
