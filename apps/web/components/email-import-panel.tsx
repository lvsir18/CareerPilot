"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusPill } from "@/components/status-pill";
import {
  confirmApplicationImport,
  uploadApplicationEmail,
} from "@/lib/client-api";
import type {
  ApplicationImportPreview,
  ApplicationRecord,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  APPLICATION_STATUS_OPTIONS,
  formatApplicationStatus,
} from "@/lib/job-display";

export function EmailImportPanel({ applications }: { applications: ApplicationRecord[] }) {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [batch, setBatch] = useState<
    { filename: string; ok: boolean; duplicate: boolean; message: string }[]
  >([]);
  const [preview, setPreview] = useState<ApplicationImportPreview | null>(null);
  const [applicationId, setApplicationId] = useState("");
  const [status, setStatus] = useState("");
  const [eventTime, setEventTime] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function handleUpload() {
    if (files.length === 0) {
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    setPreview(null);
    setBatch([]);

    const results: { filename: string; ok: boolean; duplicate: boolean; message: string }[] = [];
    let firstPreview: ApplicationImportPreview | null = null;
    for (const current of files.slice(0, 20)) {
      const result = await uploadApplicationEmail(current);
      if (!result.ok) {
        results.push({
          filename: current.name,
          ok: false,
          duplicate: false,
          message: result.error.message,
        });
        continue;
      }
      const data = result.data;
      results.push({
        filename: current.name,
        ok: true,
        duplicate: data.duplicate,
        message: data.duplicate
          ? "重复邮件，已跳过"
          : data.status === "ready"
            ? "可确认"
            : "需人工核对",
      });
      if (!data.duplicate && firstPreview === null) {
        firstPreview = data;
      }
    }
    setBusy(false);
    setBatch(results);

    if (firstPreview) {
      setPreview(firstPreview);
      setApplicationId(firstPreview.matched_application_id ?? "");
      setStatus(firstPreview.parsed_status ?? "");
      setEventTime(firstPreview.parsed_event_time ? firstPreview.parsed_event_time.slice(0, 16) : "");
    }
    setMessage(
      `已解析 ${results.length} 封邮件，成功 ${results.filter((item) => item.ok).length} 封，` +
        `重复 ${results.filter((item) => item.duplicate).length} 封，失败 ${results.filter((item) => !item.ok).length} 封。`,
    );
  }

  async function handleConfirm() {
    if (!preview) {
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await confirmApplicationImport(preview.id, {
      ...(applicationId ? { application_id: applicationId } : {}),
      ...(status ? { status } : {}),
      ...(eventTime ? { event_time: new Date(eventTime).toISOString() } : {}),
      ...(note ? { note } : {}),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setMessage("已按确认结果更新申请进度，并保留邮件佐证。");
    setPreview(null);
    setFiles([]);
    router.refresh();
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">导入招聘通知邮件</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            仅解析你主动上传的 .eml；不会执行 HTML/脚本，也不会自动修改进度。
            系统先展示提取结果，确认后才写入时间线。
          </p>
        </div>
        <StatusPill tone="info">M2-R2 · 人工确认</StatusPill>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept=".eml,message/rfc822"
          multiple
          onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          className="text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-slate-700"
        />
        <button
          type="button"
          onClick={handleUpload}
          disabled={busy || files.length === 0}
          className="rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "解析中..." : `解析邮件${files.length > 1 ? `（${files.length}）` : ""}`}
        </button>
        <span className="text-[11px] text-slate-400">单批最多 20 封，逐条显示结果</span>
      </div>

      {error ? <p className="mt-3 text-sm text-rose-700">{error}</p> : null}
      {message ? <p className="mt-3 text-sm text-emerald-700">{message}</p> : null}

      {batch.length > 0 ? (
        <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
          {batch.map((item) => (
            <li key={item.filename} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs">
              <span className="truncate text-slate-700">{item.filename}</span>
              <span
                className={
                  !item.ok
                    ? "text-rose-700"
                    : item.duplicate
                      ? "text-amber-700"
                      : "text-emerald-700"
                }
              >
                {item.message}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {preview ? (
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={preview.status === "ready" ? "ok" : "warning"}>
              {preview.status === "ready" ? "可确认" : "需人工核对"}
            </StatusPill>
            <span className="text-xs text-slate-500">
              置信度 {Math.round(preview.confidence * 100)}%
            </span>
            {preview.duplicate ? (
              <span className="text-xs text-amber-700">重复邮件</span>
            ) : null}
          </div>
          <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
            <Info label="邮件主题" value={preview.subject ?? "未提供"} />
            <Info label="发件人" value={preview.sender ?? "未提供"} />
            <Info label="企业" value={preview.parsed_company ?? "未识别，请手动选择"} />
            <Info label="岗位" value={preview.parsed_title ?? "未识别，请手动选择"} />
            <Info
              label="提取状态"
              value={preview.parsed_status ? formatApplicationStatus(preview.parsed_status) : "未明确"}
            />
            <Info
              label="邮件时间"
              value={preview.received_at ? formatDateTime(preview.received_at) : "未提供"}
            />
          </dl>
          {preview.body_excerpt ? (
            <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs leading-relaxed text-slate-600 ring-1 ring-slate-200">
              {preview.body_excerpt}
            </pre>
          ) : null}
          {preview.warnings.length ? (
            <ul className="mt-3 space-y-1 text-xs text-amber-800">
              {preview.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-medium text-slate-600">
              匹配申请（必须选择）
              <select
                value={applicationId}
                onChange={(event) => setApplicationId(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">请选择申请记录</option>
                {applications.map((application) => (
                  <option key={application.id} value={application.id}>
                    {application.external_title ?? application.job?.title ?? "未命名岗位"}
                    {" · "}
                    {application.external_company ?? application.job?.company ?? "公司未知"}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-600">
              确认状态
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">使用邮件提取（无则必须选择）</option>
                {APPLICATION_STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {formatApplicationStatus(option)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-slate-600">
              发生时间（可选）
              <input
                type="datetime-local"
                value={eventTime}
                onChange={(event) => setEventTime(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs font-medium text-slate-600">
              备注（可选）
              <input
                value={note}
                onChange={(event) => setNote(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
          </div>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={busy || !applicationId}
            className="mt-4 rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy ? "写入中..." : "确认并写入进度"}
          </button>
          <p className="mt-2 text-[11px] text-slate-500">
            打开官网或收到邮件本身不会自动标记；必须由你确认。邮件未明确的状态不会被自动推断。
          </p>
        </div>
      ) : null}
    </section>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="mt-0.5 font-medium text-slate-800">{value}</dd>
    </div>
  );
}
