import { Activity, Database, Server } from "lucide-react";
import type { ReactNode } from "react";

import { StatusPill, type StatusTone } from "@/components/status-pill";
import type { DependencyCheck, ReadinessSnapshot } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type CardState = "ok" | "error" | "unknown";

const STATE_TEXT: Record<CardState, string> = {
  ok: "正常",
  error: "不可用",
  unknown: "未检测",
};

const STATE_TONE: Record<CardState, StatusTone> = {
  ok: "ok",
  error: "error",
  unknown: "neutral",
};

const DETAIL_TEXT: Record<CardState, string> = {
  ok: "连接正常",
  error: "依赖不可用",
  unknown: "尚未执行检查",
};

function checkState(checks: DependencyCheck[], name: string): CardState {
  const check = checks.find((item) => item.name === name);
  if (!check) {
    return "unknown";
  }
  return check.status === "ok" ? "ok" : "error";
}

function StatusCard({
  icon,
  label,
  state,
  detail,
  hint,
}: {
  icon: ReactNode;
  label: string;
  state: CardState;
  detail?: string;
  hint: string;
}) {
  return (
    <div className="bg-white px-6 py-5">
      <div className="flex items-center justify-between gap-3">
        <dt className="flex items-center gap-2 text-xs font-medium tracking-wide text-slate-500 uppercase">
          <span className="text-slate-400">{icon}</span>
          {label}
        </dt>
        <StatusPill tone={STATE_TONE[state]}>{STATE_TEXT[state]}</StatusPill>
      </div>
      <dd className="mt-3 text-sm font-medium text-slate-900">{detail ?? DETAIL_TEXT[state]}</dd>
      <p className="mt-1 text-xs leading-relaxed text-slate-500">{hint}</p>
    </div>
  );
}

export function SystemStatusPanel({ readiness }: { readiness: ReadinessSnapshot }) {
  const apiState: CardState = readiness.reachable
    ? "ok"
    : "error";

  return (
    <section
      aria-labelledby="system-status-title"
      className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-6 py-5">
        <div>
          <h2 id="system-status-title" className="text-sm font-semibold text-slate-900">
            系统状态
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            实时探测 <code className="font-mono">/healthz</code> 与{" "}
            <code className="font-mono">/readyz</code>
          </p>
        </div>
        <StatusPill tone={readiness.ready ? "ok" : readiness.reachable ? "warning" : "error"}>
          {readiness.ready ? "依赖就绪" : readiness.reachable ? "依赖异常" : "API 不可达"}
        </StatusPill>
      </div>

      <dl className="grid gap-px bg-slate-100 sm:grid-cols-3">
        <StatusCard
          icon={<Activity className="size-3.5" aria-hidden />}
          label="API 服务"
          state={apiState}
          detail={readiness.reachable ? "进程存活" : "无法连接"}
          hint="FastAPI 进程存活，不依赖数据库"
        />
        <StatusCard
          icon={<Database className="size-3.5" aria-hidden />}
          label="数据库"
          state={checkState(readiness.checks, "database")}
          hint="PostgreSQL · pgvector 预留"
        />
        <StatusCard
          icon={<Server className="size-3.5" aria-hidden />}
          label="Redis"
          state={checkState(readiness.checks, "redis")}
          hint="Celery broker 与任务队列"
        />
      </dl>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/60 px-6 py-3 text-xs text-slate-500">
        <span>检查时间：{formatDateTime(readiness.checkedAt)}</span>
        {readiness.error ? (
          <span className="font-mono text-rose-600">{readiness.error.code}</span>
        ) : (
          <span className="font-mono text-emerald-700">all_dependencies_ok</span>
        )}
      </div>
    </section>
  );
}
