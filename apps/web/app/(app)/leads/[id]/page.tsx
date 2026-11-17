"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ArrowUpRight, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { getJobLead, verifyJobLead } from "@/lib/client-api";
import type { JobLeadDetail } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { formatEvidenceKind, formatLeadStatus, verificationTone } from "@/lib/job-display";
import { RegisterLeadButton } from "@/components/register-lead-button";

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const leadId = params?.id ?? "";
  const [detail, setDetail] = useState<JobLeadDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function load(id: string) {
    setStatus("loading");
    setError(null);
    const result = await getJobLead(id);
    if (!result.ok) {
      setError(
        result.error.status === 404
          ? "这条候选岗位不存在，或不属于当前账号。"
          : result.error.message,
      );
      setStatus("error");
      return;
    }
    setDetail(result.data);
    setStatus("ready");
  }

  useEffect(() => {
    if (!leadId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void load(leadId);
  }, [leadId]);

  async function handleVerify() {
    if (!detail) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await verifyJobLead(detail.lead.id);
    if (!result.ok) {
      setBusy(false);
      setError(result.error.message);
      return;
    }
    const refreshed = await getJobLead(detail.lead.id);
    setBusy(false);
    if (refreshed.ok) {
      setDetail(refreshed.data);
    }
    setNotice(
      refreshed.ok && refreshed.data.lead.job_id
        ? "核验成功，已生成可匹配的岗位记录，可在岗位详情查看匹配结果。"
        : "核验请求已提交。",
    );
  }

  if (status === "loading") {
    return <p className="text-sm text-slate-500">正在加载候选岗位…</p>;
  }

  if (status === "error" || !detail) {
    return (
      <div className="space-y-4">
        <Link
          href="/discover"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          返回招聘中心
        </Link>
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-5">
          <p className="break-words text-sm text-rose-800">{error ?? "候选岗位加载失败"}</p>
          <button
            type="button"
            onClick={() => void load(leadId)}
            className="mt-3 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
          >
            <RefreshCw className="size-3" aria-hidden />
            重新加载
          </button>
        </div>
      </div>
    );
  }

  const lead = detail.lead;

  return (
    <div className="space-y-6">
      <Link
        href="/discover"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        返回招聘中心
      </Link>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill tone={verificationTone(lead.verification_status)}>
                {formatLeadStatus(lead.verification_status)}
              </StatusPill>
              {lead.is_private ? (
                <span className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-500 ring-1 ring-slate-200 ring-inset">
                  仅本人可见
                </span>
              ) : null}
            </div>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">
              {lead.title}
            </h1>
            <p className="mt-1 text-sm text-slate-600">{lead.company}</p>
            <p className="mt-2 text-xs text-slate-500">
              保存时间：{formatDateTime(lead.first_seen_at)}
              {lead.published_date ? ` · 来源标注发布：${lead.published_date}` : ""}
            </p>
            {lead.last_verification_error ? (
              <p className="mt-3 break-words rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                最近一次核验未成功：{lead.last_verification_error}
              </p>
            ) : null}
          </header>

          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">你保存的 JD</h2>
            {lead.summary ? (
              <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-700">
                {lead.summary}
              </p>
            ) : (
              <p className="mt-3 text-sm text-slate-500">
                这条候选只有链接与标题，没有正文。可在“导入岗位”里补充 JD。
              </p>
            )}
          </section>

          {notice ? (
            <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              {notice}
            </p>
          ) : null}
          {error ? (
            <p className="break-words rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
              {error}
            </p>
          ) : null}
        </div>

        <aside className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">下一步</h2>
            {lead.job_id ? (
              <Link
                href={`/jobs/${lead.job_id}`}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white"
              >
                打开已核验岗位详情
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => void handleVerify()}
                disabled={busy}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40"
              >
                <ShieldCheck className="size-4" aria-hidden />
                {busy ? "核验中..." : "尝试核验官方页面"}
              </button>
            )}
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
              核验只读取你提交的这一个官方公开页面，不会登录或批量抓取。
            </p>
            <RegisterLeadButton
              leadId={lead.id}
              company={lead.company}
              title={lead.title}
            />
            <div className="mt-3 flex flex-wrap gap-3 text-xs">
              <Link href="/discover" className="text-slate-600 hover:underline">
                返回招聘中心
              </Link>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">来源</h2>
            <a
              href={lead.official_url}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-sky-700"
            >
              打开原始页面
              <ArrowUpRight className="size-4" aria-hidden />
            </a>
            <p className="mt-2 break-all text-[11px] text-slate-500">{lead.official_url}</p>
          </section>

          {detail.evidence.length > 0 ? (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">来源证据</h2>
              <ul className="mt-3 space-y-2 text-xs text-slate-600">
                {detail.evidence.map((item) => (
                  <li key={item.id} className="rounded-lg bg-slate-50 p-2.5">
                    <p className="font-medium text-slate-800">{formatEvidenceKind(item.evidence_kind)}</p>
                    <p className="mt-0.5 break-all text-slate-500">{item.source_url}</p>
                    <p className="mt-0.5 text-slate-400">{formatDateTime(item.captured_at)}</p>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}