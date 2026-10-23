"use client";

import { CircleAlert } from "lucide-react";

export default function DashboardError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto mt-16 max-w-lg rounded-2xl border border-rose-200 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-rose-50 text-rose-500">
        <CircleAlert className="size-5" aria-hidden />
      </div>
      <h1 className="mt-4 text-lg font-semibold text-slate-900">页面加载失败</h1>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">
        无法渲染概览页面。请检查后端服务是否运行，或稍后重试。
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-5 inline-flex rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700"
      >
        重新加载
      </button>
    </div>
  );
}
