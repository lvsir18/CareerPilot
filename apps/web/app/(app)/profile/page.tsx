"use client";

import { Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

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

const EXPERIENCE_KINDS = [
  { value: "internship", label: "实习" },
  { value: "project", label: "项目" },
  { value: "research", label: "科研" },
  { value: "competition", label: "竞赛" },
  { value: "open_source", label: "开源" },
  { value: "work", label: "工作" },
  { value: "other", label: "其他" },
];

const JOB_TYPES = [
  { value: "internship", label: "实习" },
  { value: "campus", label: "校园招聘" },
  { value: "full_time", label: "全职" },
];

interface EducationDraft {
  school: string;
  degree: string;
  major: string;
  start_year: string;
  graduation_year: string;
}

interface ExperienceDraft {
  kind: string;
  title: string;
  time_range: string;
  skills: string;
  description: string;
}

interface ProjectDraft {
  title: string;
  summary: string;
}

function toNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function splitList(value: string): string[] {
  return value
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function eduDrafts(profile: Profile): EducationDraft[] {
  return profile.education.map((item) => ({
    school: item.school ?? "",
    degree: item.degree ?? "",
    major: item.major ?? "",
    start_year: item.start_year ? String(item.start_year) : "",
    graduation_year: item.graduation_year ? String(item.graduation_year) : "",
  }));
}

function expDrafts(profile: Profile): ExperienceDraft[] {
  return profile.experiences.map((item) => ({
    kind: item.kind ?? "other",
    title: item.title ?? "",
    time_range: item.time_range ?? "",
    skills: item.skills.join(", "),
    description: item.description ?? "",
  }));
}

function projectDrafts(profile: Profile): ProjectDraft[] {
  return profile.projects.map((item) => ({ title: item.title, summary: item.summary ?? "" }));
}

function isBlank(profile: Profile): boolean {
  const prefs = profile.preferences;
  const hasPrefs = Boolean(
    prefs.target_roles.length ||
      prefs.cities.length ||
      prefs.job_types.length ||
      prefs.graduation_year ||
      prefs.keywords.length,
  );
  return (
    !profile.headline &&
    profile.education.length === 0 &&
    profile.skills.length === 0 &&
    profile.experiences.length === 0 &&
    profile.projects.length === 0 &&
    !hasPrefs
  );
}

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100";

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);

  const [headline, setHeadline] = useState("");
  const [skills, setSkills] = useState("");
  const [education, setEducation] = useState<EducationDraft[]>([]);
  const [experiences, setExperiences] = useState<ExperienceDraft[]>([]);
  const [projects, setProjects] = useState<ProjectDraft[]>([]);
  const [targetRoles, setTargetRoles] = useState<string[]>([]);
  const [cities, setCities] = useState("");
  const [jobTypes, setJobTypes] = useState<string[]>([]);
  const [graduationYear, setGraduationYear] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const hydrate = useCallback((data: Profile) => {
    setProfile(data);
    setHeadline(data.headline ?? "");
    setSkills(data.skills.join(", "));
    setEducation(eduDrafts(data));
    setExperiences(expDrafts(data));
    setProjects(projectDrafts(data));
    setTargetRoles(data.preferences.target_roles);
    setCities(data.preferences.cities.join(", "));
    setJobTypes(data.preferences.job_types);
    setGraduationYear(data.preferences.graduation_year ? String(data.preferences.graduation_year) : "");
  }, []);

  const load = useCallback(async () => {
    setStatus("loading");
    setLoadError(null);
    const result = await getProfile();
    if (!result.ok) {
      setStatus("error");
      setLoadError(result.error.message);
      return;
    }
    hydrate(result.data);
    setStatus("ready");
  }, [hydrate]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void load();
  }, [load]);

  function toggle(value: string, list: string[], set: (items: string[]) => void) {
    set(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  /** Persist the form; returns the stored profile or null when it failed. */
  async function persist(): Promise<Profile | null> {
    const result = await updateProfile({
      headline: headline.trim() || null,
      education: education
        .map((item) => ({
          school: item.school.trim() || null,
          degree: item.degree.trim() || null,
          major: item.major.trim() || null,
          start_year: toNumber(item.start_year),
          graduation_year: toNumber(item.graduation_year),
        }))
        .filter((item) => item.school || item.degree || item.major || item.start_year),
      skills: splitList(skills),
      experiences: experiences
        .map((item) => ({
          kind: item.kind,
          title: item.title.trim() || null,
          time_range: item.time_range.trim() || null,
          skills: splitList(item.skills),
          description: item.description.trim() || null,
        }))
        .filter((item) => item.title || item.description),
      projects: projects
        .map((item) => ({ title: item.title.trim(), summary: item.summary.trim() || null }))
        .filter((item) => item.title),
      preferences: {
        ...(profile?.preferences ?? {}),
        target_roles: targetRoles,
        cities: splitList(cities),
        job_types: jobTypes,
        graduation_year: graduationYear ? Number(graduationYear) : null,
      },
    });
    if (!result.ok) {
      setError(result.error.message);
      return null;
    }
    hydrate(result.data);
    setStatus("ready");
    return result.data;
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    setNotice(null);
    const saved = await persist();
    setBusy(false);
    if (!saved) {
      return;
    }
    setNotice(
      saved.verified_by_user
        ? "画像已更新。"
        : "画像已更新，内容有变化，需要重新确认后才能用于岗位匹配。",
    );
  }

  async function handleConfirm() {
    setBusy(true);
    setError(null);
    setNotice(null);
    // Confirming without saving would drop the edits the user just typed, so the
    // draft is written first and only a stored profile is confirmed.
    const saved = await persist();
    if (!saved) {
      setBusy(false);
      return;
    }
    const result = await confirmProfile();
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    hydrate(result.data);
    setStatus("ready");
    setNotice("画像已保存并确认，可以查看岗位推荐了。");
  }

  if (status === "loading") {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-sm text-slate-500">正在加载画像…</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 shadow-sm">
        <h1 className="text-base font-semibold text-rose-900">画像读取失败</h1>
        <p className="mt-2 break-words text-sm text-rose-800">
          {loadError ?? "服务暂时不可用，请稍后重试。"}
        </p>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-3 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          <RefreshCw className="size-4" aria-hidden />
          重新加载
        </button>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-sm text-slate-500">暂时没有画像数据。</p>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-3 inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700"
        >
          <RefreshCw className="size-4" aria-hidden />
          重新加载
        </button>
      </div>
    );
  }

  const empty = isBlank(profile);

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-slate-900">我的画像</h1>
            <p className="mt-1 text-xs text-slate-500">
              版本 {profile.version}
              {profile.verified_by_user && profile.confirmed_at
                ? ` · 已确认于 ${new Date(profile.confirmed_at).toLocaleString()}`
                : " · 当前版本尚未确认，确认后才能用于岗位匹配"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleConfirm()}
            disabled={busy || profile.verified_by_user}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            <ShieldCheck className="size-4" aria-hidden />
            {profile.verified_by_user ? "已确认" : "确认画像"}
          </button>
        </div>
        {error ? <p className="mt-3 break-words text-sm text-rose-700">{error}</p> : null}
        {notice ? <p className="mt-3 break-words text-sm text-emerald-700">{notice}</p> : null}
      </section>

      {empty ? (
        <section className="rounded-xl border border-sky-200 bg-sky-50 p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-sky-900">画像还是空的</h2>
          <p className="mt-1 text-xs text-sky-800">
            可以先上传简历自动解析，再回到这里逐项核对和修正；也可以直接在下方手动填写。
          </p>
          <Link
            href="/resumes"
            className="mt-3 inline-block rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
          >
            去导入简历
          </Link>
        </section>
      ) : null}

      <section className="space-y-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">基本信息与技能</h2>
          <div className="mt-3 grid gap-3">
            <label className="block">
              <span className="text-xs font-medium text-slate-600">一句话简介</span>
              <input
                value={headline}
                onChange={(event) => setHeadline(event.target.value)}
                placeholder="计算机专业本科生，方向为大模型应用与后端"
                className={inputClass}
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-600">技术技能（逗号分隔）</span>
              <input
                value={skills}
                onChange={(event) => setSkills(event.target.value)}
                placeholder="Python, PyTorch, 大模型, RAG"
                className={inputClass}
              />
            </label>
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800">教育经历</h2>
            <button
              type="button"
              onClick={() =>
                setEducation((prev) => [
                  ...prev,
                  { school: "", degree: "", major: "", start_year: "", graduation_year: "" },
                ])
              }
              className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700"
            >
              <Plus className="size-3" aria-hidden />
              添加教育经历
            </button>
          </div>
          {education.length === 0 ? (
            <p className="mt-2 text-xs text-slate-400">
              没有解析到教育经历。学历、专业和毕业年份会影响岗位资格判断，建议手动补充。
            </p>
          ) : null}
          <div className="mt-3 space-y-3">
            {education.map((item, index) => (
              <div key={index} className="rounded-lg border border-slate-200 p-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="block">
                    <span className="text-xs font-medium text-slate-600">学校</span>
                    <input
                      value={item.school}
                      onChange={(event) =>
                        setEducation((prev) =>
                          prev.map((row, i) =>
                            i === index ? { ...row, school: event.target.value } : row,
                          ),
                        )
                      }
                      placeholder="测试大学"
                      className={inputClass}
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-600">专业</span>
                    <input
                      value={item.major}
                      onChange={(event) =>
                        setEducation((prev) =>
                          prev.map((row, i) =>
                            i === index ? { ...row, major: event.target.value } : row,
                          ),
                        )
                      }
                      placeholder="计算机科学与技术"
                      className={inputClass}
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-600">学历</span>
                    <input
                      value={item.degree}
                      onChange={(event) =>
                        setEducation((prev) =>
                          prev.map((row, i) =>
                            i === index ? { ...row, degree: event.target.value } : row,
                          ),
                        )
                      }
                      placeholder="本科 / 硕士 / 博士"
                      className={inputClass}
                    />
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="block">
                      <span className="text-xs font-medium text-slate-600">入学年份</span>
                      <input
                        value={item.start_year}
                        onChange={(event) =>
                          setEducation((prev) =>
                            prev.map((row, i) =>
                              i === index ? { ...row, start_year: event.target.value } : row,
                            ),
                          )
                        }
                        placeholder="2023"
                        className={inputClass}
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs font-medium text-slate-600">毕业年份</span>
                      <input
                        value={item.graduation_year}
                        onChange={(event) =>
                          setEducation((prev) =>
                            prev.map((row, i) =>
                              i === index ? { ...row, graduation_year: event.target.value } : row,
                            ),
                          )
                        }
                        placeholder="2027"
                        className={inputClass}
                      />
                    </label>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setEducation((prev) => prev.filter((_, i) => i !== index))}
                  className="mt-2 inline-flex items-center gap-1 text-xs text-rose-600"
                >
                  <Trash2 className="size-3" aria-hidden />
                  删除这条教育经历
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800">实习与项目经历</h2>
            <button
              type="button"
              onClick={() =>
                setExperiences((prev) => [
                  ...prev,
                  { kind: "internship", title: "", time_range: "", skills: "", description: "" },
                ])
              }
              className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700"
            >
              <Plus className="size-3" aria-hidden />
              添加经历
            </button>
          </div>
          {experiences.length === 0 ? (
            <p className="mt-2 text-xs text-slate-400">还没有经历条目，匹配时会缺少证据。</p>
          ) : null}
          <div className="mt-3 space-y-3">
            {experiences.map((item, index) => (
              <div key={index} className="rounded-lg border border-slate-200 p-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="block">
                    <span className="text-xs font-medium text-slate-600">类型</span>
                    <select
                      value={item.kind}
                      onChange={(event) =>
                        setExperiences((prev) =>
                          prev.map((row, i) =>
                            i === index ? { ...row, kind: event.target.value } : row,
                          ),
                        )
                      }
                      className={inputClass}
                    >
                      {EXPERIENCE_KINDS.map((kind) => (
                        <option key={kind.value} value={kind.value}>
                          {kind.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-600">名称 / 岗位</span>
                    <input
                      value={item.title}
                      onChange={(event) =>
                        setExperiences((prev) =>
                          prev.map((row, i) =>
                            i === index ? { ...row, title: event.target.value } : row,
                          ),
                        )
                      }
                      placeholder="大模型应用实习生"
                      className={inputClass}
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-600">时间范围</span>
                    <input
                      value={item.time_range}
                      onChange={(event) =>
                        setExperiences((prev) =>
                          prev.map((row, i) =>
                            i === index ? { ...row, time_range: event.target.value } : row,
                          ),
                        )
                      }
                      placeholder="2025.06-2025.09"
                      className={inputClass}
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-600">相关技能（逗号分隔）</span>
                    <input
                      value={item.skills}
                      onChange={(event) =>
                        setExperiences((prev) =>
                          prev.map((row, i) =>
                            i === index ? { ...row, skills: event.target.value } : row,
                          ),
                        )
                      }
                      placeholder="Python, LangGraph"
                      className={inputClass}
                    />
                  </label>
                </div>
                <label className="mt-3 block">
                  <span className="text-xs font-medium text-slate-600">描述</span>
                  <textarea
                    value={item.description}
                    rows={2}
                    onChange={(event) =>
                      setExperiences((prev) =>
                        prev.map((row, i) =>
                          i === index ? { ...row, description: event.target.value } : row,
                        ),
                      )
                    }
                    placeholder="负责什么、做出了什么结果"
                    className={inputClass}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setExperiences((prev) => prev.filter((_, i) => i !== index))}
                  className="mt-2 inline-flex items-center gap-1 text-xs text-rose-600"
                >
                  <Trash2 className="size-3" aria-hidden />
                  删除这条经历
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800">项目</h2>
            <button
              type="button"
              onClick={() => setProjects((prev) => [...prev, { title: "", summary: "" }])}
              className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700"
            >
              <Plus className="size-3" aria-hidden />
              添加项目
            </button>
          </div>
          {projects.length === 0 ? (
            <p className="mt-2 text-xs text-slate-400">还没有项目条目。</p>
          ) : null}
          <div className="mt-3 space-y-3">
            {projects.map((item, index) => (
              <div key={index} className="rounded-lg border border-slate-200 p-3">
                <label className="block">
                  <span className="text-xs font-medium text-slate-600">项目名称</span>
                  <input
                    value={item.title}
                    onChange={(event) =>
                      setProjects((prev) =>
                        prev.map((row, i) =>
                          i === index ? { ...row, title: event.target.value } : row,
                        ),
                      )
                    }
                    placeholder="CareerPilot"
                    className={inputClass}
                  />
                </label>
                <label className="mt-3 block">
                  <span className="text-xs font-medium text-slate-600">说明</span>
                  <textarea
                    value={item.summary}
                    rows={2}
                    onChange={(event) =>
                      setProjects((prev) =>
                        prev.map((row, i) =>
                          i === index ? { ...row, summary: event.target.value } : row,
                        ),
                      )
                    }
                    className={inputClass}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setProjects((prev) => prev.filter((_, i) => i !== index))}
                  className="mt-2 inline-flex items-center gap-1 text-xs text-rose-600"
                >
                  <Trash2 className="size-3" aria-hidden />
                  删除这个项目
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-800">求职偏好</h2>
        <div>
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

        <div className="grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="text-xs font-medium text-slate-600">期望城市（逗号分隔）</span>
            <input
              value={cities}
              onChange={(event) => setCities(event.target.value)}
              placeholder="北京, 上海"
              className={inputClass}
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-slate-600">毕业年份</span>
            <input
              value={graduationYear}
              onChange={(event) => setGraduationYear(event.target.value)}
              placeholder="2027"
              className={inputClass}
            />
          </label>
        </div>

        <div>
          <span className="text-xs font-medium text-slate-600">求职类型</span>
          <div className="mt-1 flex flex-wrap gap-2">
            {JOB_TYPES.map((item) => (
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
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "保存中..." : "保存画像"}
        </button>
      </section>
    </div>
  );
}