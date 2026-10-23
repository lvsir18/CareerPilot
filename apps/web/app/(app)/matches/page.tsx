"use client";

import { ArrowUpRight, Check, Star } from "lucide-react";
import { useEffect, useState } from "react";

import { createApplication, getRecommendations, saveJob } from "@/lib/client-api";
import type { RecommendationItem } from "@/lib/api";

const ELIGIBILITY_LABEL: Record<string, string> = {
  eligible: "符合资格",
  ineligible: "不符合资格",
  unknown: "待进一步确认",
};

export default function MatchesPage() {
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setBusy(true);
    setError(null);
    const result = await getRecommendations({ exclude_applied: false });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setItems(result.data.data);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void refresh();
  }, []);

  async function handleSave(jobId: string) {
    await saveJob(jobId, "saved");
    await refresh();
  }

  async function handleApply(jobId: string) {
    await createApplication(jobId);
    await refresh();
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h1 className="text-base font-semibold text-slate-900">智能岗位推荐</h1>
        <p className="mt-1 text-xs text-slate-500">
          基于已确认画像与完整 JD 的可解释匹配，分数不是录取概率。
        </p>
        {error ? <p className="mt-3 text-sm text-rose-700">{error}</p> : null}
      </section>

      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {busy
            ? "计算中..."
            : "暂无推荐。请先上传简历、确认画像，或等待已核验岗位产生。"}
        </p>
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <article
              key={item.job.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-semibold text-slate-900">{item.job.company}</span>
                <span className="text-slate-700">{item.job.title}</span>
                <span className="text-xs text-slate-500">
                  {item.job.city ?? "城市未知"} · {item.job.job_type ?? "类型未知"}
                </span>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="rounded-lg bg-slate-900 px-3 py-1 text-sm font-bold text-white">
                  {item.match.match_score != null
                    ? `${item.match.match_score}/100`
                    : "信息不足"}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] ring-1 ${
                    item.match.eligibility_status === "ineligible"
                      ? "bg-rose-50 text-rose-700 ring-rose-200"
                      : item.match.eligibility_status === "eligible"
                        ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                        : "bg-slate-50 text-slate-600 ring-slate-200"
                  }`}
                >
                  {ELIGIBILITY_LABEL[item.match.eligibility_status] ?? item.match.eligibility_status}
                </span>
                {item.applied_status ? (
                  <span className="text-xs text-slate-500">已申请：{item.applied_status}</span>
                ) : null}
              </div>

              {item.match.match_score != null ? (
                <div className="mt-4 grid gap-3 text-xs md:grid-cols-2">
                  <div>
                    <p className="font-medium text-slate-600">符合要求</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {item.match.matched_skills.length ? (
                        item.match.matched_skills.map((skill) => (
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
                      {item.match.unverified_skills.length ? (
                        item.match.unverified_skills.map((skill) => (
                          <span
                            key={skill}
                            className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600"
                          >
                            {skill}
                          </span>
                        ))
                      ) : (
                        <span className="text-slate-400">暂无</span>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-xs text-slate-500">招聘信息不完整，仅提供基础匹配。</p>
              )}

              <p className="mt-3 text-xs leading-relaxed text-slate-600">
                推荐原因：{item.match.explanation || "暂无解释"}
              </p>
              {item.match.eligibility_reasons.length ? (
                <ul className="mt-2 space-y-0.5 text-xs text-rose-600">
                  {item.match.eligibility_reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}

              <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
                <a
                  href={item.job.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1 font-medium text-sky-700 hover:underline"
                >
                  查看官网
                  <ArrowUpRight className="size-3" aria-hidden />
                </a>
                {!item.saved ? (
                  <button
                    type="button"
                    onClick={() => void handleSave(item.job.id)}
                    className="inline-flex items-center gap-1 text-slate-700 hover:underline"
                  >
                    <Star className="size-3" aria-hidden />
                    收藏
                  </button>
                ) : (
                  <span className="text-slate-400">已收藏</span>
                )}
                {!item.applied_status ? (
                  <button
                    type="button"
                    onClick={() => void handleApply(item.job.id)}
                    className="text-slate-700 hover:underline"
                  >
                    登记申请进度
                  </button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
