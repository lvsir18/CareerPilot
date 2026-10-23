import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StatusTone = "ok" | "info" | "warning" | "error" | "neutral";

const TONE_STYLES: Record<StatusTone, { wrapper: string; dot: string }> = {
  ok: { wrapper: "bg-emerald-50 text-emerald-700 ring-emerald-600/10", dot: "bg-emerald-500" },
  info: { wrapper: "bg-sky-50 text-sky-700 ring-sky-600/10", dot: "bg-sky-500" },
  warning: { wrapper: "bg-amber-50 text-amber-700 ring-amber-600/10", dot: "bg-amber-500" },
  error: { wrapper: "bg-rose-50 text-rose-700 ring-rose-600/10", dot: "bg-rose-500" },
  neutral: { wrapper: "bg-slate-100 text-slate-600 ring-slate-500/10", dot: "bg-slate-400" },
};

export function StatusPill({
  tone,
  children,
  className,
}: {
  tone: StatusTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset",
        TONE_STYLES[tone].wrapper,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", TONE_STYLES[tone].dot)} aria-hidden />
      {children}
    </span>
  );
}
