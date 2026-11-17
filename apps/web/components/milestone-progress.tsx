import { Check, CircleDashed } from "lucide-react";

import { StatusPill, type StatusTone } from "@/components/status-pill";
import { MILESTONES, type MilestoneStatus } from "@/lib/milestones";
import { cn } from "@/lib/utils";

const STATUS_META: Record<MilestoneStatus, { label: string; tone: StatusTone }> = {
  done: { label: "已完成", tone: "ok" },
  next: { label: "下一步", tone: "warning" },
  planned: { label: "规划中", tone: "neutral" },
};

export function MilestoneProgress() {
  return (
    <section
      aria-labelledby="milestone-title"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="milestone-title" className="text-sm font-semibold text-slate-900">
            交付里程碑
          </h2>
          <p className="mt-1 text-xs text-slate-500">按规范顺序推进，每个里程碑先通过测试再进入下一阶段</p>
        </div>
        <StatusPill tone="neutral">1 / 7 完成</StatusPill>
      </div>

      <ol className="mt-6 space-y-4">
        {MILESTONES.map((milestone) => {
          const meta = STATUS_META[milestone.status];
          const expanded = milestone.status !== "planned";
          return (
            <li key={milestone.id} className="flex gap-3">
              <span
                className={cn(
                  "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
                  milestone.status === "done" && "border-emerald-200 bg-emerald-50 text-emerald-700",
                  milestone.status === "next" && "border-amber-200 bg-amber-50 text-amber-700",
                  milestone.status === "planned" && "border-slate-200 bg-slate-50 text-slate-400",
                )}
              >
                {milestone.status === "done" ? (
                  <Check className="size-3.5" aria-hidden />
                ) : (
                  <CircleDashed className="size-3.5" aria-hidden />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-slate-400">{milestone.id}</span>
                  <span
                    className={cn(
                      "text-sm font-medium",
                      milestone.status === "planned" ? "text-slate-500" : "text-slate-900",
                    )}
                  >
                    {milestone.title}
                  </span>
                  <StatusPill tone={meta.tone}>{meta.label}</StatusPill>
                </div>
                {expanded ? (
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {milestone.items.map((item) => (
                      <li
                        key={item}
                        className="rounded-md bg-slate-50 px-2 py-1 text-xs text-slate-600 ring-1 ring-slate-200/70 ring-inset"
                      >
                        {item}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
