"use client";

import { Check, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { getProfile, matchJob } from "@/lib/client-api";
import type { RecommendationItem } from "@/lib/api";
import { formatEligibility } from "@/lib/job-display";

type State = "loading" | "need_confirm" | "error" | "ready";

export function JobMatchPanel({ jobId }: { jobId: string }) {
  const [state, setState] = useState<State>("loading");
  const [item, setItem] = useState<RecommendationItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setState("loading");
    setError(null);
    const profile = await getProfile();
    if (!profile.ok) {
      setState("error");
      setError(profile.error.message);
      return;
    }
    if (!profile.data.verified_by_user) {
      setState("need_confirm");
      return;
    }
    const result = await matchJob(jobId);
    if (!result.ok) {
      setState("error");
      setError(result.error.message);
      return;
    }
    setItem(result.data);
    setState("ready");
  }, [jobId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void run();
  }, [run]);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Sparkles className="size-4 text-sky-600" aria-hidden />
        与我的画像匹配
      </div>

      {state === "loading" ? <p className="mt-3 text-sm text-slate-500">正在计算匹配…</p> : null}

      {state === "need_confirm" ? (
        <div className="mt-3">
          <p className="text-sm leading-relaxed text-slate-600">
            匹配需要一份已确认的画像。确认后即可在这个岗位页直接看到分数、符合与暂未体现的能力。
          </p>
          <Link
            href="/profile"
            className="mt-3 inline-block rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
          >
            去确认画像
          </Link>
        </div>
      ) : null}

      {state === "error" ? (
        <div className="mt-3">
          <p className="flex items-center gap-1.5 break-words text-sm text-rose-700">
            <ShieldAlert className="size-4 shrink-0" aria-hidden />
            {error ?? "匹配计算失败"}
          </p>
          <button
            type="button"
            onClick={() => void run()}
            className="mt-3 inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-700"
          >
            <RefreshCw className="size-3" aria-hidden />
            重新计算
          </button>
        </div>
      ) : null}

      {state === "ready" && item ? (
        <div className="mt-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-lg bg-slate-900 px-3 py-1 text-sm font-bold text-white">
              {item.match.match_score != null ? `${item.match.match_score}/100` : "信息不足"}
            </span>
            <span className="rounded-full bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200 ring-inset">
              {formatEligibility(item.match.eligibility_status)}
            </span>
            {item.saved ? <span className="text-xs text-slate-400">已收藏</span> : null}
            {item.applied_status ? (
              <span className="text-xs text-slate-500">已登记申请</span>
            ) : null}
          </div>

          {(item.match.eligibility_reasons ?? []).length ? (
            <ul className="mt-2 space-y-0.5 text-xs text-rose-600">
              {(item.match.eligibility_reasons ?? []).map((reason) => (
                <li key={reason} className="break-words">
                  {reason}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="mt-4 grid gap-3 text-xs md:grid-cols-2">
            <div>
              <p className="font-medium text-slate-600">符合要求</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(item.match.matched_skills ?? []).length ? (
                  (item.match.matched_skills ?? []).map((skill) => (
                    <span
                      key={skill}
                      className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700"
                    >
                      <Check className="size-3" aria-hidden />
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="text-slate-400">未识别到明确匹配技能</span>
                )}
              </div>
            </div>
            <div>
              <p className="font-medium text-slate-600">简历暂未体现</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(item.match.unverified_skills ?? []).length ? (
                  (item.match.unverified_skills ?? []).map((skill) => (
                    <span key={skill} className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="text-slate-400">暂无</span>
                )}
              </div>
            </div>
          </div>

          <p className="mt-3 break-words text-xs leading-relaxed text-slate-600">
            {item.match.explanation || "暂无解释"}
          </p>
          <p className="mt-2 text-[11px] text-slate-400">
            分数反映画像与 JD 的证据重合度，不代表录取概率；请以原始 JD 为准。
          </p>
        </div>
      ) : null}
    </section>
  );
}