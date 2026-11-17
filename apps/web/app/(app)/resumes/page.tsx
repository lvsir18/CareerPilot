"use client";

import { FileUp, RefreshCw, Trash2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import {
  applyResumeToProfile,
  deleteResume,
  listResumes,
  setPrimaryResume,
  uploadResume,
} from "@/lib/client-api";
import type { Resume } from "@/lib/api";

export default function ResumesPage() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function refresh() {
    const result = await listResumes();
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setResumes(result.data);
  }

  useEffect(() => {
    let ignore = false;
    void listResumes().then((result) => {
      if (ignore) return;
      if (result.ok) setResumes(result.data);
      else setError(result.error.message);
    });
    return () => {
      ignore = true;
    };
  }, []);

  async function handleUpload(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    const result = await uploadResume(file);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    // A failed extraction is still an accepted upload: say so precisely instead
    // of a green "已上传并解析" next to a "解析失败" card.
    setNotice(
      result.data.parse_status === "success"
        ? `已上传并解析：${file.name}`
        : `文件已保存，但没能从 ${file.name} 提取到文字（可能是扫描版）。可以改用文字版 PDF/DOCX，或直接在「我的画像」手工填写。`,
    );
    await refresh();
  }

  async function handleApply(resume: Resume) {
    setBusy(true);
    setError(null);
    const result = await applyResumeToProfile(resume.id);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setNotice("已将简历解析结果应用到画像，请前往「我的画像」查看并确认。");
  }

  async function handlePrimary(resume: Resume) {
    const result = await setPrimaryResume(resume.id);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    await refresh();
  }

  async function handleDelete(resume: Resume) {
    const result = await deleteResume(resume.id);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    await refresh();
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-slate-900">简历管理</h1>
            <p className="mt-1 text-xs text-slate-500">
              上传 PDF 或 DOCX，系统会提取教育、技能和经历，供画像确认使用。
            </p>
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
            <FileUp className="size-4" aria-hidden />
            {busy ? "解析中..." : "上传简历"}
            <input
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              disabled={busy}
              onChange={(event) => void handleUpload(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        {error ? <p className="mt-3 text-sm text-rose-700">{error}</p> : null}
        {notice ? <p className="mt-3 text-sm text-emerald-700">{notice}</p> : null}
      </section>

      <section className="space-y-3">
        {resumes.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
            尚未上传简历。
          </p>
        ) : (
          resumes.map((resume) => (
            <article
              key={resume.id}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-900">{resume.filename}</span>
                {resume.is_primary ? (
                  <span className="rounded bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700 ring-1 ring-sky-200 ring-inset">
                    主要来源
                  </span>
                ) : null}
                <span
                  className={`rounded px-2 py-0.5 text-[11px] ${
                    resume.parse_status === "success"
                      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 ring-inset"
                      : "bg-rose-50 text-rose-700 ring-1 ring-rose-200 ring-inset"
                  }`}
                >
                  {resume.parse_status === "success" ? "解析成功" : "解析失败"}
                </span>
              </div>

              {resume.parse_status === "success" ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {resume.parsed.skills.slice(0, 12).map((skill) => (
                    <span
                      key={skill}
                      className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-rose-600">{resume.error}</p>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                {resume.parse_status === "success" ? (
                  <button
                    type="button"
                    onClick={() => void handleApply(resume)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 text-sky-700 hover:underline disabled:opacity-40"
                  >
                    <UserRound className="size-3" aria-hidden />
                    应用到画像
                  </button>
                ) : null}
                {!resume.is_primary ? (
                  <button
                    type="button"
                    onClick={() => void handlePrimary(resume)}
                    className="text-slate-600 hover:underline"
                  >
                    设为主要来源
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => void handleDelete(resume)}
                  className="inline-flex items-center gap-1 text-rose-600 hover:underline"
                >
                  <Trash2 className="size-3" aria-hidden />
                  删除
                </button>
              </div>
            </article>
          ))
        )}
      </section>

      <button
        type="button"
        onClick={() => void refresh()}
        className="inline-flex items-center gap-1 text-xs text-slate-500 hover:underline"
      >
        <RefreshCw className="size-3" aria-hidden />
        刷新
      </button>
    </div>
  );
}
