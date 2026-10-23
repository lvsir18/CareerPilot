"use client";

import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { confirmProfile, getProfile, updateProfile } from "@/lib/client-api";
import type { Profile } from "@/lib/api";

const JOB_FAMILIES = [
  { value: "llm_agent", label: "LLM / Agent" },
  { value: "algorithm_data", label: "算法 / 数据" },
  { value: "backend", label: "后端 / 基础架构" },
  { value: "frontend", label: "前端 / 客户端" },
  { value: "product", label: "产品" },
  { value: "design", label: "设计" },
  { value: "operations", label: "运营 / 综合" },
  { value: "other", label: "其他" },
];

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [skills, setSkills] = useState("");
  const [targetRoles, setTargetRoles] = useState<string[]>([]);
  const [cities, setCities] = useState("");
  const [jobTypes, setJobTypes] = useState<string[]>([]);
  const [graduationYear, setGraduationYear] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function refresh() {
    const result = await getProfile();
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    const data = result.data;
    setProfile(data);
    setSkills(data.skills.join(", "));
    setTargetRoles(data.preferences.target_roles);
    setCities(data.preferences.cities.join(", "));
    setJobTypes(data.preferences.job_types);
    setGraduationYear(data.preferences.graduation_year ? String(data.preferences.graduation_year) : "");
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void refresh();
  }, []);

  function toggle(value: string, list: string[], set: (items: string[]) => void) {
    set(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await updateProfile({
      skills: skills.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
      preferences: {
        target_roles: targetRoles,
        cities: cities.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
        job_types: jobTypes,
        graduation_year: graduationYear ? Number(graduationYear) : null,
      },
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setNotice("画像已更新，请确认以用于岗位匹配。");
    await refresh();
  }

  async function handleConfirm() {
    setBusy(true);
    setError(null);
    const result = await confirmProfile();
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setNotice("画像已确认，可以查看岗位推荐了。");
    await refresh();
  }

  if (!profile) {
    return <p className="text-sm text-slate-500">加载中...</p>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-slate-900">我的画像</h1>
            <p className="mt-1 text-xs text-slate-500">
              版本 {profile.version}
              {profile.confirmed_at
                ? ` · 已确认于 ${new Date(profile.confirmed_at).toLocaleString()}`
                : " · 尚未确认"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleConfirm()}
            disabled={busy || profile.verified_by_user}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            <ShieldCheck className="size-4" aria-hidden />
            {profile.verified_by_user ? "已确认" : "确认画像"}
          </button>
        </div>
        {error ? <p className="mt-3 text-sm text-rose-700">{error}</p> : null}
        {notice ? <p className="mt-3 text-sm text-emerald-700">{notice}</p> : null}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <label className="block">
          <span className="text-xs font-medium text-slate-600">技术技能（逗号分隔）</span>
          <input
            value={skills}
            onChange={(event) => setSkills(event.target.value)}
            placeholder="Python, PyTorch, 大模型, RAG"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          />
        </label>

        <div className="mt-4">
          <span className="text-xs font-medium text-slate-600">目标岗位方向</span>
          <div className="mt-1 flex flex-wrap gap-2">
            {JOB_FAMILIES.map((family) => (
              <button
                key={family.value}
                type="button"
                onClick={() => toggle(family.value, targetRoles, setTargetRoles)}
                className={`rounded-full px-3 py-1 text-xs ring-1 ${
                  targetRoles.includes(family.value)
                    ? "bg-sky-50 text-sky-700 ring-sky-300"
                    : "bg-white text-slate-600 ring-slate-200"
                }`}
              >
                {family.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="text-xs font-medium text-slate-600">期望城市（逗号分隔）</span>
            <input
              value={cities}
              onChange={(event) => setCities(event.target.value)}
              placeholder="北京, 上海"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-slate-600">毕业年份</span>
            <input
              value={graduationYear}
              onChange={(event) => setGraduationYear(event.target.value)}
              placeholder="2027"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            />
          </label>
        </div>

        <div className="mt-4">
          <span className="text-xs font-medium text-slate-600">求职类型</span>
          <div className="mt-1 flex flex-wrap gap-2">
            {[
              { value: "internship", label: "实习" },
              { value: "campus", label: "校园招聘" },
              { value: "full_time", label: "全职" },
            ].map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => toggle(item.value, jobTypes, setJobTypes)}
                className={`rounded-full px-3 py-1 text-xs ring-1 ${
                  jobTypes.includes(item.value)
                    ? "bg-sky-50 text-sky-700 ring-sky-300"
                    : "bg-white text-slate-600 ring-slate-200"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={busy}
          className="mt-5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "保存中..." : "保存画像"}
        </button>
      </section>
    </div>
  );
}
