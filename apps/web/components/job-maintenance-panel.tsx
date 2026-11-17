"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Archive, RefreshCw, X } from "lucide-react";

import {
  cancelJobMaintenance,
  getActivity,
  getJobMaintenance,
  getLatestJobMaintenance,
  getOfficialSources,
  previewJobPrune,
  startJobMaintenance,
  startJobPrune,
} from "@/lib/client-api";
import type {
  MaintenanceItem,
  MaintenanceRun,
  MaintenanceScope,
  OfficialSourceCompany,
  PrunePreview,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const TERMINAL = new Set(["success", "partial", "failed", "cancelled"]);

const OUTCOME_LABEL: Record<string, string> = {
  created: "新增",
  updated: "内容更新",
  unchanged: "内容未变",
  closed: "确认下线",
  reopened: "恢复在招",
  unconfirmed: "无法确认",
  unsupported: "不支持",
  archived: "已归档",
  restored: "已恢复",
};

function outcomeLabel(value: string): string {
  return OUTCOME_LABEL[value] ?? value;
}

export function JobMaintenancePanel({
  scope,
  total,
  isAdmin,
  archivedView,
}: {
  scope: MaintenanceScope;
  total: number;
  isAdmin: boolean;
  archivedView: boolean;
}) {
  const router = useRouter();
  const [dialog, setDialog] = useState<"refresh" | "prune" | null>(null);
  const [recheck, setRecheck] = useState(true);
  const [discover, setDiscover] = useState(false);
  const [sources, setSources] = useState<OfficialSourceCompany[]>([]);
  const [latestRun, setLatestRun] = useState<MaintenanceRun | null>(null);
  const [maxJobs, setMaxJobs] = useState(100);
  const [cooldownHours, setCooldownHours] = useState(6);
  const [discoverDepth, setDiscoverDepth] = useState<"quick" | "standard" | "deep">("standard");
  const [run, setRun] = useState<MaintenanceRun | null>(null);
  const [preview, setPreview] = useState<PrunePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the capability catalogue only when the dialog opens: the list of
  // companies that cannot be discovered must be concrete, not a guess.
  useEffect(() => {
    if (dialog !== "refresh") {
      return;
    }
    void getOfficialSources().then((result) => {
      if (result.ok) {
        setSources(result.data);
      }
    });
  }, [dialog]);

  const unsupportedSources = sources
    .filter((item) => !item.supported)
    .map((item) => item.label);

  // Entering the page only re-attaches a *running* sweep. Past results stay
  // collapsed behind 「上次更新结果」 — showing yesterday's log on every visit
  // made the page look like it had just done something.
  useEffect(() => {
    let cancelled = false;
    void getActivity().then(async (snapshot) => {
      if (cancelled || !snapshot.ok || !snapshot.data.job_maintenance) {
        return;
      }
      const result = await getJobMaintenance(snapshot.data.job_maintenance.run_id);
      if (!cancelled && result.ok) {
        setRun(result.data);
      }
    });
    void getLatestJobMaintenance().then((latest) => {
      if (!cancelled && latest.ok && latest.data) {
        setLatestRun(latest.data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!run || TERMINAL.has(run.status)) {
      if (run && TERMINAL.has(run.status)) {
        router.refresh();
      }
      return;
    }
    const timer = setInterval(async () => {
      const result = await getJobMaintenance(run.id);
      if (result.ok) {
        setRun(result.data);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [run, router]);

  async function submitRefresh() {
    setBusy(true);
    setError(null);
    const result = await startJobMaintenance({
      kind: discover ? "discover" : "refresh",
      scope,
      recheck,
      discover,
      max_jobs: maxJobs,
      cooldown_hours: cooldownHours,
      discover_depth: discoverDepth,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    const created = await getJobMaintenance(result.data.run_id);
    setRun(created.ok ? created.data : null);
    // The dialog is a launcher: close it so the progress panel underneath is
    // visible (a modal that stays open hid the very progress it started).
    setDialog(null);
  }

  async function openPrune() {
    setDialog("prune");
    setError(null);
    setPreview(null);
    setBusy(true);
    const result = await previewJobPrune(scope);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setPreview(result.data);
  }

  async function submitPrune() {
    setBusy(true);
    setError(null);
    const result = await startJobPrune(scope);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    const created = await getJobMaintenance(result.data.run_id);
    setRun(created.ok ? created.data : null);
    if (created.ok) {
      setLatestRun(created.data);
    }
    setDialog(null);
  }

  async function stopRun() {
    if (!run) return;
    await cancelJobMaintenance(run.id);
  }

  const counters = run?.progress.counters ?? run?.result.counters ?? {};
  const running = run !== null && !TERMINAL.has(run.status);
  const progressTotal = run?.progress.total ?? 0;
  const processed = run?.progress.processed ?? 0;

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            setDialog("refresh");
            setError(null);
          }}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:border-slate-400"
        >
          <RefreshCw className="size-3.5" aria-hidden />
          更新岗位
        </button>
        {latestRun && !run ? (
          <button
            type="button"
            onClick={() => setRun(latestRun)}
            className="text-xs text-slate-500 hover:underline"
          >
            上次更新结果
            {latestRun.finished_at ? ` · ${formatDateTime(latestRun.finished_at)}` : ""}
          </button>
        ) : null}
        {isAdmin ? (
          <button
            type="button"
            onClick={() => void openPrune()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:border-slate-400"
          >
            <Archive className="size-3.5" aria-hidden />
            清理已下线
          </button>
        ) : null}
      </div>

      {run ? (
        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-slate-800">
              {run.kind === "prune" ? "清理已下线" : "更新岗位"} · {run.status}
              {running ? null : (
                <span className="ml-1.5 text-xs font-normal text-slate-400">
                  {run.finished_at ? formatDateTime(run.finished_at) : ""}
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              {running ? (
                <button
                  type="button"
                  onClick={() => void stopRun()}
                  className="text-xs text-rose-600 hover:underline"
                >
                  取消任务
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setRun(null)}
                  className="text-xs text-slate-500 hover:underline"
                >
                  收起
                </button>
              )}
            </div>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {progressTotal > 0
              ? `${processed} / ${progressTotal}`
              : run.progress.current || "等待执行"}
            {run.progress.current && progressTotal > 0 ? ` · ${run.progress.current}` : ""}
          </p>
          {Object.keys(counters).length ? (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
              {Object.entries(counters).map(([key, value]) => (
                <span key={key}>
                  {outcomeLabel(key)} <span className="font-medium text-slate-900">{value}</span>
                </span>
              ))}
            </div>
          ) : null}
          {run.result.unsupported?.length ? (
            <p className="mt-2 text-xs text-amber-700">
              不支持自动发现：{run.result.unsupported.map((item) => item.name).join("、")}
            </p>
          ) : null}
          {run.result.items?.length ? (
            <ul className="mt-2 max-h-40 divide-y divide-slate-100 overflow-y-auto text-xs">
              {run.result.items.slice(0, 50).map((item, index) => (
                <li key={`${item.job_id ?? item.title}-${index}`} className="flex gap-2 py-1">
                  <span className="w-16 shrink-0 text-slate-500">{outcomeLabel(item.outcome)}</span>
                  <span className="min-w-0 flex-1 truncate text-slate-700">
                    {item.company} · {item.title}
                    {item.reason ? (
                      <span className="ml-1 text-slate-400">（{item.reason}）</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {dialog ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-base font-semibold text-slate-900">
                {dialog === "refresh" ? "更新岗位" : "清理已下线"}
              </h2>
              <button
                type="button"
                onClick={() => {
                  setDialog(null);
                  setPreview(null);
                }}
                aria-label="关闭"
                className="rounded-md p-1 text-slate-400 hover:text-slate-700"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>

            {dialog === "refresh" ? (
              <div className="mt-4 space-y-3 text-sm">
                <p className="text-slate-600">
                  当前筛选共 <span className="font-medium text-slate-900">{total}</span>{" "}
                  个岗位；本次最多复核{" "}
                  <span className="font-medium text-slate-900">{maxJobs}</span> 个
                  （按最久未检查优先，连续执行会继续往后覆盖）。
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="text-xs text-slate-600">
                    单次复核上限
                    <select
                      value={maxJobs}
                      onChange={(event) => setMaxJobs(Number(event.target.value))}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
                    >
                      <option value={40}>40 个</option>
                      <option value={100}>100 个</option>
                      <option value={200}>200 个（上限）</option>
                    </select>
                  </label>
                  <label className="text-xs text-slate-600">
                    跳过最近已复核
                    <select
                      value={cooldownHours}
                      onChange={(event) => setCooldownHours(Number(event.target.value))}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
                    >
                      <option value={0}>不跳过</option>
                      <option value={6}>6 小时</option>
                      <option value={24}>24 小时</option>
                      <option value={72}>3 天</option>
                    </select>
                  </label>
                </div>
                <p className="text-xs text-slate-400">
                  复核失败的岗位不受“跳过”限制，下次会优先重试。
                </p>
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={recheck}
                    onChange={(event) => setRecheck(event.target.checked)}
                    className="mt-0.5 size-4 accent-sky-600"
                  />
                  <span>
                    复核已有岗位
                    <span className="block text-xs text-slate-500">
                      重新读取官方详情，更新 JD、城市、招聘类型与在招状态
                    </span>
                  </span>
                </label>
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={discover}
                    onChange={(event) => setDiscover(event.target.checked)}
                    className="mt-0.5 size-4 accent-sky-600"
                  />
                  <span>
                    发现新增岗位
                    <span className="block text-xs text-slate-500">
                      从已适配官网检索并入库；会按多个方向（大模型 / 算法 / 后端 / 前端 / 数据）
                      逐轮抓取，已有岗位只更新，不新建
                    </span>
                  </span>
                </label>
                {discover ? (
                  <label className="block text-xs text-slate-600">
                    发现深度
                    <select
                      value={discoverDepth}
                      onChange={(event) =>
                        setDiscoverDepth(event.target.value as "quick" | "standard" | "deep")
                      }
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
                    >
                      <option value="quick">快速 · 每家 10 个岗位 / 1 个关键词</option>
                      <option value="standard">标准 · 每家 30 个岗位 / 3 个关键词</option>
                      <option value="deep">深度 · 每家 50 个岗位 / 6 个关键词</option>
                    </select>
                    <span className="mt-1 block text-[11px] text-slate-400">
                      越深越慢，但能翻到列表更里面的岗位；只抓官方招聘站公开列表，不发实时搜索请求。
                    </span>
                  </label>
                ) : null}
                {unsupportedSources.length ? (
                  <p className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                    不支持自动发现：{unsupportedSources.join("、")}
                  </p>
                ) : null}
                {error ? <p className="text-xs text-rose-700">{error}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setDialog(null)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={busy || (!recheck && !discover)}
                    onClick={() => void submitRefresh()}
                    className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                  >
                    {busy ? "提交中…" : "开始"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-4 space-y-3 text-sm">
                {busy ? <p className="text-slate-500">正在统计…</p> : null}
                {preview ? (
                  <>
                    <p className="text-slate-600">
                      有明确下线证据的岗位共{" "}
                      <span className="font-medium text-slate-900">{preview.count}</span> 个，将软归档（保留收藏、申请与历史）。
                      {preview.truncated ? "单次最多归档 100 个。" : ""}
                    </p>
                    <ul className="max-h-48 divide-y divide-slate-100 overflow-y-auto text-xs">
                      {preview.items.map((item: MaintenanceItem) => (
                        <li key={item.job_id ?? item.title} className="py-1.5">
                          <p className="text-slate-800">
                            {item.company} · {item.title}
                          </p>
                          <p className="text-slate-500">
                            检查于 {item.closed_checked_at ? formatDateTime(item.closed_checked_at) : "未知"}
                            {item.closed_evidence ? ` · ${item.closed_evidence}` : ""}
                          </p>
                        </li>
                      ))}
                    </ul>
                    {preview.count === 0 ? (
                      <p className="text-xs text-slate-500">当前没有可清理的岗位。</p>
                    ) : null}
                  </>
                ) : null}
                {error ? <p className="text-xs text-rose-700">{error}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setDialog(null);
                      setPreview(null);
                    }}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={busy || !preview || preview.count === 0}
                    onClick={() => void submitPrune()}
                    className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                  >
                    确认清理
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {archivedView ? null : null}
    </>
  );
}
