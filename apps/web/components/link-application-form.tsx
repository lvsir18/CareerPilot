"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createApplicationRecord } from "@/lib/client-api";
import {
  APPLICATION_STATUS_OPTIONS,
  formatApplicationStatus,
} from "@/lib/job-display";

export function LinkApplicationForm() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState("planned");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await createApplicationRecord({
      external_company: company.trim(),
      external_title: title.trim(),
      external_url: url.trim(),
      status,
      ...(notes.trim() ? { notes: notes.trim() } : {}),
    });
    setBusy(false);
    if (!result.ok) {
      setError(
        result.error.code === "APPLICATION_EXISTS"
          ? "该岗位已有申请记录，无需重复登记。"
          : result.error.message,
      );
      return;
    }
    setMessage("已登记。请在官网自行完成申请，并回来更新真实进度。");
    setCompany("");
    setTitle("");
    setUrl("");
    setNotes("");
    router.refresh();
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:border-slate-400"
      >
        仅登记官方链接
      </button>
    );
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">登记仅官方链接的岗位</h3>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-slate-500 hover:text-slate-800"
        >
          收起
        </button>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        适用于招聘网站没有进入 CareerPilot 岗位库的申请。登记不会触发外部投递。
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Field label="公司" value={company} onChange={setCompany} />
        <Field label="岗位名称" value={title} onChange={setTitle} />
        <Field label="官方链接" value={url} onChange={setUrl} />
        <label className="text-xs font-medium text-slate-600">
          当前状态
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            {APPLICATION_STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {formatApplicationStatus(option)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="mt-2 block text-xs font-medium text-slate-600">
        备注（可选）
        <input
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
        />
      </label>
      <button
        type="button"
        onClick={submit}
        disabled={busy || !company.trim() || !title.trim() || !url.trim()}
        className="mt-3 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {busy ? "保存中..." : "登记申请"}
      </button>
      {error ? <p className="mt-2 text-xs text-rose-700">{error}</p> : null}
      {message ? <p className="mt-2 text-xs text-emerald-700">{message}</p> : null}
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-xs font-medium text-slate-600">
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
      />
    </label>
  );
}
