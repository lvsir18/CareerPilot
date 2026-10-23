"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { importJob, importJobLead, previewJobImport } from "@/lib/client-api";
import type { JobImportPreview } from "@/lib/api";

type Mode = "public_page" | "manual_paste";

interface PasteFields {
  company: string;
  title: string;
  city: string;
  location_text: string;
  job_type: string;
  recruitment_program: string;
  description: string;
  requirements: string;
}

const EMPTY_FIELDS: PasteFields = {
  company: "百度",
  title: "",
  city: "",
  location_text: "",
  job_type: "internship",
  recruitment_program: "",
  description: "",
  requirements: "",
};

export function JobImportForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<JobImportPreview | null>(null);
  const [mode, setMode] = useState<Mode>("public_page");
  const [fields, setFields] = useState<PasteFields>(EMPTY_FIELDS);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateField<K extends keyof PasteFields>(key: K, value: PasteFields[K]) {
    setFields((current) => ({ ...current, [key]: value }));
  }

  async function handlePreview() {
    setBusy(true);
    setError(null);
    setMessage(null);
    setPreview(null);
    const result = await previewJobImport(url.trim());
    setBusy(false);
    if (!result.ok) {
      setMode("manual_paste");
      setError(`${result.error.message}。可在下方粘贴 JD 后确认入库。`);
      return;
    }
    setPreview(result.data);
    setMode("public_page");
    setFields((current) => ({
      ...current,
      company: result.data.company,
      title: result.data.title,
      city: result.data.city ?? "",
      location_text: result.data.location_text ?? "",
      job_type: result.data.job_type ?? "unknown",
      recruitment_program: result.data.recruitment_program ?? "",
      description: result.data.description ?? "",
      requirements: result.data.requirements.join("\n"),
    }));
    setMessage("解析成功。请核对字段后确认入库。");
  }

  async function handleImport() {
    setBusy(true);
    setError(null);
    setMessage(null);

    if (mode === "manual_paste") {
      const leadResult = await importJobLead({
        url: url.trim(),
        title: fields.title,
        company: fields.company,
        city: fields.city || undefined,
        job_type: fields.job_type || undefined,
        description: [
          fields.description,
          fields.requirements ? `\n\n任职要求：\n${fields.requirements}` : "",
        ]
          .join("")
          .trim(),
      });
      setBusy(false);
      if (!leadResult.ok) {
        setError(leadResult.error.message);
        return;
      }
      router.push("/discover");
      router.refresh();
      return;
    }

    const result = await importJob({
      url: url.trim(),
      mode: "public_page",
      confirmed: true,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    router.push(`/jobs/${result.data.id}`);
    router.refresh();
  }

  return (
    <div className="mt-6 space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <label htmlFor="job-url" className="text-sm font-medium text-slate-800">
          官方岗位链接
        </label>
        <p className="mt-1 text-xs text-slate-500">
          仅支持 <code className="font-mono">https://talent.baidu.com/jobs/detail/...</code>。
          一次只读取一个页面。
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            id="job-url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://talent.baidu.com/jobs/detail/INTERN/..."
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          />
          <button
            type="button"
            onClick={handlePreview}
            disabled={busy || !url.trim()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "解析中..." : "解析页面"}
          </button>
        </div>

        {message ? <p className="mt-3 text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-3 text-sm text-rose-700">{error}</p> : null}
      </section>

      {preview ? (
        <section className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800">
              官方页面已核验
            </span>
            <span className="text-xs text-slate-500">
              岗位 ID：<span className="font-mono">{preview.source_job_id}</span>
            </span>
          </div>
          <h2 className="mt-3 text-lg font-semibold text-slate-900">{preview.title}</h2>
          <p className="mt-1 text-sm text-slate-600">
            {preview.company} · {preview.city ?? "城市未知"} · {preview.job_type ?? "类型未知"}
          </p>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-slate-500">招聘项目</dt>
              <dd className="mt-0.5 text-slate-800">{preview.recruitment_program ?? "未提供"}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">发布时间</dt>
              <dd className="mt-0.5 text-slate-800">{preview.published_at ?? "未提供"}</dd>
            </div>
          </dl>
          {preview.warnings.length ? (
            <ul className="mt-3 space-y-1 text-xs text-amber-800">
              {preview.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">
              查看解析出的 JD
            </summary>
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs leading-relaxed text-slate-700 ring-1 ring-slate-200">
              {preview.description ?? "未提供职位描述"}
            </pre>
          </details>
        </section>
      ) : null}

      {mode === "manual_paste" ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50/40 p-5">
          <h2 className="text-sm font-semibold text-slate-900">粘贴 JD 并确认</h2>
          <p className="mt-1 text-xs text-slate-600">
            仅在无法读取官方页面时使用。入库会标记为“用户已确认”，不会伪称为自动核验。
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="公司" value={fields.company} onChange={(v) => updateField("company", v)} />
            <Field label="岗位名称" value={fields.title} onChange={(v) => updateField("title", v)} />
            <Field label="城市" value={fields.city} onChange={(v) => updateField("city", v)} />
            <Field
              label="工作地点原文"
              value={fields.location_text}
              onChange={(v) => updateField("location_text", v)}
            />
            <Field
              label="招聘项目"
              value={fields.recruitment_program}
              onChange={(v) => updateField("recruitment_program", v)}
            />
            <Field label="岗位类型" value={fields.job_type} onChange={(v) => updateField("job_type", v)} />
          </div>
          <label htmlFor="pasted-description" className="mt-4 block text-sm font-medium text-slate-800">
            职位描述（必填）
          </label>
          <textarea
            id="pasted-description"
            value={fields.description}
            onChange={(event) => updateField("description", event.target.value)}
            rows={8}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          />
          <label htmlFor="pasted-requirements" className="mt-3 block text-sm font-medium text-slate-800">
            任职要求（每行一条）
          </label>
          <textarea
            id="pasted-requirements"
            value={fields.requirements}
            onChange={(event) => updateField("requirements", event.target.value)}
            rows={4}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          />
        </section>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleImport}
          disabled={busy || !url.trim()}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "处理中..." : mode === "public_page" ? "确认并入库" : "保存为私有候选"}
        </button>
        <p className="text-xs text-slate-500">
          官方页面解析成功后写入可检索岗位库；粘贴 JD 仅本人可见，标记为用户导入。
        </p>
      </div>
    </div>
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
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
      />
    </label>
  );
}
