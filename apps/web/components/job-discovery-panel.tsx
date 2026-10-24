"use client";

import Link from "next/link";
import { ArrowUpRight, LayoutGrid, Lock, Search, ShieldCheck, Table2 } from "lucide-react";
import { useEffect, useState } from "react";

import { CreateApplicationButton } from "@/components/create-application-button";
import { JobCard } from "@/components/job-card";
import { StatusPill } from "@/components/status-pill";
import {
  discoverJobs,
  getOfficialSources,
  searchOfficialJobs,
  verifyJobLead,
} from "@/lib/client-api";
import type { DiscoveryResponse, JobLead, OfficialSourceCompany } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  formatJobFamily,
  verificationTone,
} from "@/lib/job-display";

const OFFICIAL_COMPANIES = [
  { key: "tencent", label: "腾讯" },
  { key: "bytedance", label: "字节跳动" },
  { key: "xiaohongshu", label: "小红书" },
  { key: "bilibili", label: "哔哩哔哩" },
  { key: "meituan", label: "美团" },
];

/** Used only when the capability catalog cannot be loaded. */
const FALLBACK_OFFICIAL_SOURCES: OfficialSourceCompany[] = OFFICIAL_COMPANIES.map((item) => ({
  key: item.key,
  label: item.label,
  supported: true,
  mode: "rendered",
  note: "",
}));

const COMPANIES = [
  { value: "bytedance", label: "字节跳动", priority: "P0" },
  { value: "tencent", label: "腾讯", priority: "P0" },
  { value: "alibaba", label: "阿里巴巴", priority: "P0" },
  { value: "baidu", label: "百度", priority: "P0" },
  { value: "meituan", label: "美团", priority: "P0" },
  { value: "xiaohongshu", label: "小红书", priority: "P0" },
  { value: "bilibili", label: "哔哩哔哩", priority: "P0" },
  { value: "dewu", label: "得物", priority: "P0" },
  { value: "deepseek", label: "DeepSeek", priority: "P0" },
  { value: "360", label: "360", priority: "P0" },
  { value: "xiaomi", label: "小米", priority: "P1" },
  { value: "minimax", label: "MiniMax", priority: "P1" },
  { value: "jd", label: "京东", priority: "P1" },
  { value: "kimi", label: "月之暗面 Kimi", priority: "P1" },
  { value: "ctrip", label: "携程", priority: "P1" },
  { value: "kuaishou", label: "快手", priority: "P1" },
  { value: "netease", label: "网易", priority: "P1" },
  { value: "huawei", label: "华为", priority: "P1" },
  { value: "pdd", label: "拼多多", priority: "P1" },
];
const DEFAULT_COMPANIES = COMPANIES.filter((item) => item.priority === "P0").map(
  (item) => item.value,
);

const JOB_TYPES = [
  { value: "", label: "全部类型" },
  { value: "internship", label: "实习" },
  { value: "campus", label: "校招" },
];

const JOB_FAMILIES = [
  { value: "", label: "全部方向" },
  { value: "llm_agent", label: "LLM / Agent" },
  { value: "algorithm_data", label: "算法 / 数据" },
  { value: "backend", label: "后端 / 基础架构" },
  { value: "frontend", label: "前端 / 客户端" },
  { value: "product", label: "产品" },
  { value: "design", label: "设计" },
  { value: "operations", label: "运营 / 综合" },
  { value: "other", label: "其他" },
];

function formatCompany(company: string): string {
  const labels: Record<string, string> = {
    bytedance: "字节跳动",
    tencent: "腾讯",
    alibaba: "阿里巴巴",
    baidu: "百度",
    meituan: "美团",
    xiaohongshu: "小红书",
    bilibili: "哔哩哔哩",
    dewu: "得物",
    deepseek: "DeepSeek",
    "360": "360",
    xiaomi: "小米",
    minimax: "MiniMax",
    jd: "京东",
    kimi: "月之暗面 Kimi",
    ctrip: "携程",
    kuaishou: "快手",
    netease: "网易",
    huawei: "华为",
    pdd: "拼多多",
  };
  return labels[company] ?? company;
}

function readUrlFilter(key: string): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(key);
}

export function JobDiscoveryPanel() {
  const [query, setQuery] = useState(() => readUrlFilter("q") ?? "实习");
  const [companies, setCompanies] = useState<string[]>(() => {
    const raw = readUrlFilter("companies");
    return raw ? raw.split(",").filter(Boolean) : DEFAULT_COMPANIES;
  });
  const [city, setCity] = useState(() => readUrlFilter("city") ?? "");
  const [jobType, setJobType] = useState(() => readUrlFilter("job_type") ?? "");
  const [jobFamily, setJobFamily] = useState(() => readUrlFilter("job_family") ?? "");
  const [verification, setVerification] = useState(() => readUrlFilter("verification") ?? "all");
  const [publishedWithin, setPublishedWithin] = useState(() => readUrlFilter("published_within") ?? "");
  const [days, setDays] = useState(() => readUrlFilter("days") ?? "7");
  const [sort, setSort] = useState(() => readUrlFilter("sort") ?? "relevance");
  const [view, setView] = useState<"cards" | "table">(() =>
    readUrlFilter("view") === "table" ? "table" : "cards",
  );
  const [result, setResult] = useState<DiscoveryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingVerify, setPendingVerify] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [officialKeyword, setOfficialKeyword] = useState(() => readUrlFilter("q") ?? "");

  // Hand-off carries the filters the user just chose; otherwise the Agent
  // silently widened the search to every company and city.
  // Every selected company is transmitted; truncating here dropped real search
  // constraints (a 10-company default became 5).
  const handedOffFilters = [
    companies.length ? `企业：${companies.map(formatCompany).join("、")}` : "",
    city ? `城市：${city}` : "",
    jobType ? `类型：${JOB_TYPES.find((item) => item.value === jobType)?.label ?? jobType}` : "",
    jobFamily
      ? `方向：${JOB_FAMILIES.find((item) => item.value === jobFamily)?.label ?? jobFamily}`
      : "",
  ].filter(Boolean);
  const agentQuery = [
    query ? `关键词「${query}」` : "",
    ...handedOffFilters,
  ]
    .filter(Boolean)
    .join("；");
  const agentHref = `/agent?q=${encodeURIComponent(
    agentQuery
      ? `帮我找岗位：${agentQuery}。请沿用这些条件，不要扩大范围。`
      : "帮我找实习岗位",
  )}`;
  const [officialCompanies, setOfficialCompanies] = useState<string[]>(["tencent"]);
  const [tencentProject, setTencentProject] = useState("日常实习");
  const [officialBusy, setOfficialBusy] = useState(false);
  const [officialNotice, setOfficialNotice] = useState<string | null>(null);
  // Which companies can actually be searched by direct connection comes from the
  // backend catalog, so the UI never offers a button that is guaranteed to fail.
  const [officialSources, setOfficialSources] = useState<OfficialSourceCompany[]>([]);
  const [followFilter, setFollowFilter] = useState(true);

  useEffect(() => {
    let active = true;
    void getOfficialSources().then((result) => {
      if (!active || !result.ok) return;
      setOfficialSources(result.data);
    });
    return () => {
      active = false;
    };
  }, []);

  const catalog = officialSources.length ? officialSources : FALLBACK_OFFICIAL_SOURCES;
  const supportedKeys = officialSources.filter((item) => item.supported).map((item) => item.key);
  const supportedKeySignature = supportedKeys.join(",");

  // "跟随上方筛选" keeps the two company lists in sync: pick 字节+美团 above and
  // the direct-connection row follows instead of silently keeping 腾讯.
  useEffect(() => {
    if (!followFilter || !supportedKeySignature) return;
    const allowed = supportedKeySignature.split(",");
    const next = companies.filter((key) => allowed.includes(key));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- derived from the filter above
    setOfficialCompanies(next.length ? next : allowed.slice(0, 1));
  }, [companies, followFilter, supportedKeySignature]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (companies.length && companies.join(",") !== DEFAULT_COMPANIES.join(",")) {
      params.set("companies", companies.join(","));
    }
    if (city) params.set("city", city);
    if (jobType) params.set("job_type", jobType);
    if (jobFamily) params.set("job_family", jobFamily);
    if (verification !== "all") params.set("verification", verification);
    if (publishedWithin) params.set("published_within", publishedWithin);
    if (days) params.set("days", days);
    if (sort !== "relevance") params.set("sort", sort);
    if (view !== "cards") params.set("view", view);
    const next = params.toString();
    window.history.replaceState(null, "", next ? `?${next}` : window.location.pathname);
  }, [query, companies, city, jobType, jobFamily, verification, publishedWithin, days, sort, view]);

  function toggleCompany(value: string) {
    setCompanies((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }

  async function runSearch(page = 1) {
    if (companies.length === 0) {
      setError("至少选择一家企业。");
      return;
    }
    setBusy(true);
    setError(null);
    const response = await discoverJobs({
      query: query.trim() || undefined,
      companies,
      city: city.trim() || undefined,
      job_type: jobType || undefined,
      job_family: jobFamily || undefined,
      verification: verification === "all" ? undefined : verification,
      published_within_days: publishedWithin ? Number(publishedWithin) : undefined,
      days: days ? Number(days) : undefined,
      sort,
      page,
      page_size: 20,
    });
    setBusy(false);
    if (!response.ok) {
      setError(response.error.message);
      return;
    }
    setResult(response.data);
  }

  async function runOfficialSearch() {
    if (!officialCompanies.length) {
      setOfficialNotice("请至少选择一家企业");
      return;
    }
    setOfficialBusy(true);
    setOfficialNotice(null);
    const response = await searchOfficialJobs({
      companies: officialCompanies,
      keyword: officialKeyword.trim() || undefined,
      limit: 5,
      project: officialCompanies.includes("tencent") ? tencentProject : undefined,
    });
    setOfficialBusy(false);
    if (!response.ok) {
      setOfficialNotice(`检索失败：${response.error.message}`);
      return;
    }
    const data = response.data;
    const failed = data.companies.filter((item) => item.error);
    const parts = data.companies
      .filter((item) => !item.error)
      .map((item) => `${item.label} ${item.fetched} 条`);
    const lines = [
      parts.length ? `官方直连：${parts.join("、")}` : "官方直连未返回岗位",
      `新增 ${data.created}、更新 ${data.updated}、无变化 ${data.unchanged}`,
    ];
    if (failed.length) {
      lines.push(
        `失败：${failed.map((item) => `${item.label}（${item.error}）`).join("；")}`,
      );
    }
    setOfficialNotice(`${lines.join("；")}。已写入岗位库，可在「岗位库」查看完整 JD。`);
  }

  async function verify(lead: JobLead) {
    setPendingVerify(lead.id);
    setError(null);
    const response = await verifyJobLead(lead.id);
    setPendingVerify(null);
    if (!response.ok) {
      setError(response.error.message);
      return;
    }
    await runSearch(result?.page ?? 1);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-3 md:grid-cols-12">
          <label className="md:col-span-3">
            <span className="text-xs font-medium text-slate-600">关键词</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="如 Agent 实习"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            />
          </label>
          <div className="md:col-span-5">
            <span className="text-xs font-medium text-slate-600">企业（可多选）</span>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 rounded-lg border border-slate-200 px-3 py-2">
              {COMPANIES.map((item) => (
                <label key={item.value} className="inline-flex items-center gap-1.5 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={companies.includes(item.value)}
                    onChange={() => toggleCompany(item.value)}
                    className="size-3.5 accent-sky-600"
                  />
                  {item.label}
                  <span className="text-[10px] text-slate-400">{item.priority}</span>
                </label>
              ))}
            </div>
          </div>
          <label className="md:col-span-2">
            <span className="text-xs font-medium text-slate-600">城市</span>
            <input
              value={city}
              onChange={(event) => setCity(event.target.value)}
              placeholder="北京 / 上海"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="md:col-span-2">
            <span className="text-xs font-medium text-slate-600">类型</span>
            <select
              value={jobType}
              onChange={(event) => setJobType(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              {JOB_TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="md:col-span-3">
            <span className="text-xs font-medium text-slate-600">岗位方向</span>
            <select
              value={jobFamily}
              onChange={(event) => setJobFamily(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              {JOB_FAMILIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="md:col-span-2">
            <span className="text-xs font-medium text-slate-600">核验状态</span>
            <select
              value={verification}
              onChange={(event) => setVerification(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="all">全部</option>
              <option value="verified">已核验</option>
              <option value="pending">待核验</option>
            </select>
          </label>
          <label className="md:col-span-2">
            <span className="text-xs font-medium text-slate-600">官网发布日期</span>
            <select
              value={publishedWithin}
              onChange={(event) => setPublishedWithin(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">不限/含未知</option>
              <option value="7">最近 7 天（仅已知日期）</option>
              <option value="30">最近 30 天（仅已知日期）</option>
            </select>
          </label>
          <label className="md:col-span-2">
            <span className="text-xs font-medium text-slate-600">发现窗口</span>
            <select
              value={days}
              onChange={(event) => setDays(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="7">近 7 天</option>
              <option value="30">近 30 天</option>
              <option value="">不限</option>
            </select>
          </label>
          <label className="md:col-span-3">
            <span className="text-xs font-medium text-slate-600">排序</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="relevance">相关度 / 最近发现</option>
              <option value="newest">最近发现</option>
              <option value="published">官网发布日期</option>
            </select>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => runSearch(1)}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            <Search className="size-4" aria-hidden />
            {busy ? "搜索中..." : "发现岗位"}
          </button>
          <Link href="/matches" className="text-sm text-sky-700 hover:underline">
            匹配我的简历
          </Link>
          <Link href={agentHref} className="text-sm text-sky-700 hover:underline">
            询问 Agent
          </Link>
          <Link href="/import" className="text-sm text-sky-700 hover:underline">
            手动导入官方链接 / JD
          </Link>
        </div>
        {agentQuery ? (
          <p className="mt-2 break-words text-[11px] text-slate-500">
            询问 Agent 时会带上：{agentQuery}
          </p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-rose-700">{error}</p> : null}
      </section>

      <section className="rounded-2xl border border-sky-200 bg-sky-50/50 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">企业官网直连检索</h2>
          <span className="text-[11px] text-slate-500">
            不消耗搜索额度
            {officialSources.length
              ? ` · 已支持 ${officialSources.filter((item) => item.supported).length} / ${officialSources.length} 家`
              : ""}
          </span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-600">
          这些公司的招聘页是前端渲染、抓 HTML 拿不到岗位；这里由服务端浏览器把关键词输入官方搜索框，
          读取其返回的岗位数据，拿到标题、城市、招聘类型与完整 JD。仅覆盖校招 / 实习
          （美团会先切到「应届校招」，不含社招）。灰色企业暂未适配，可用上方筛选搜索或「导入岗位」。
        </p>
        <label className="mt-2 inline-flex items-center gap-2 text-[11px] text-slate-600">
          <input
            type="checkbox"
            checked={followFilter}
            onChange={(event) => setFollowFilter(event.target.checked)}
            className="size-3.5 rounded border-slate-300"
          />
          跟随上方筛选（只取上方已勾选且支持直连的企业）
        </label>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {catalog.map((item) => {
            const active = officialCompanies.includes(item.key);
            return (
              <button
                key={item.key}
                type="button"
                aria-pressed={active}
                aria-disabled={!item.supported}
                title={item.supported ? item.note || item.label : `${item.label}：${item.note}`}
                onClick={() => {
                  if (!item.supported) {
                    const keyword = officialKeyword.trim();
                    const page = item.search_page
                      ? item.search_page.replace("{keyword}", encodeURIComponent(keyword))
                      : "";
                    if (page) {
                      window.open(page, "_blank", "noopener,noreferrer");
                    }
                    setOfficialNotice(
                      page
                        ? `${item.label} 暂不支持自动直连：${item.note}。已打开官网搜索页${
                            keyword ? `，在站内搜索「${keyword}」` : ""
                          }，找到岗位后把链接或 JD 粘到「导入岗位」，会存成仅你可见的私有候选。`
                        : `${item.label} 暂不支持自动直连：${item.note}。可用上方「筛选与搜索」，或在「导入岗位」里粘贴官方链接 / JD。`,
                    );
                    return;
                  }
                  setFollowFilter(false);
                  setOfficialCompanies((prev) =>
                    prev.includes(item.key)
                      ? prev.filter((key) => key !== item.key)
                      : [...prev, item.key],
                  );
                }}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs transition",
                  !item.supported && "border-dashed border-slate-300 bg-white text-slate-400",
                  item.supported &&
                    (active
                      ? "border-sky-600 bg-sky-600 text-white"
                      : "border-slate-300 bg-white text-slate-600 hover:border-sky-400"),
                )}
              >
                {!item.supported ? <Lock className="size-3" aria-hidden /> : null}
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="min-w-40 flex-1">
            <span className="text-xs font-medium text-slate-600">关键词</span>
            <input
              value={officialKeyword}
              onChange={(event) => setOfficialKeyword(event.target.value)}
              placeholder="算法 / 大模型 / 推荐"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          {officialCompanies.includes("tencent") ? (
            <label className="min-w-36">
              <span className="text-xs font-medium text-slate-600">腾讯招聘项目</span>
              <select
                value={tencentProject}
                onChange={(event) => setTencentProject(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="日常实习">日常实习</option>
                <option value="应届实习">应届实习</option>
                <option value="应届毕业生">应届毕业生</option>
                <option value="青云计划-应届生">青云计划-应届生</option>
                <option value="青云计划-实习生">青云计划-实习生</option>
              </select>
              <span className="mt-1 block text-[11px] text-slate-500">仅对腾讯生效</span>
            </label>
          ) : null}
          <button
            type="button"
            onClick={() => void runOfficialSearch()}
            disabled={officialBusy}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            <ArrowUpRight className="size-4" aria-hidden />
            {officialBusy ? "检索中..." : "直连检索"}
          </button>
        </div>
        {officialNotice ? (
          <p className="mt-2 break-words text-xs text-slate-700">{officialNotice}</p>
        ) : null}
      </section>

      {result ? (
        <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 text-xs leading-relaxed text-slate-600">
          <div className="flex flex-wrap items-center gap-3">
            <StatusPill tone={result.search.licensed_configured ? "ok" : "warning"}>
              {result.search.licensed_configured ? "搜索 API 已配置" : "搜索 API 未配置"}
            </StatusPill>
            <span>
              使用来源：{result.search.providers_used.join("、") || "已有库"}
            </span>
            <span>候选 {result.total_leads} 条 · 已核验岗位 {result.total_jobs} 条</span>
            <span>更新：{formatDateTime(result.search.searched_at)}</span>
            <span>
              Tavily {result.search.tavily_queries} 次请求 / 缓存 {result.search.tavily_cached_queries} 次 /
              credits 约 {result.search.credits_estimated}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            {result.search.provider_statuses.map((provider) => (
              <span key={provider.name} className="inline-flex items-center gap-1">
                <span
                  className={`size-1.5 rounded-full ${
                    provider.available ? "bg-emerald-500" : "bg-rose-400"
                  }`}
                  aria-hidden
                />
                {provider.label}
                <span className="text-slate-400">
                  {provider.available
                    ? provider.enabled
                      ? provider.configured
                        ? "可用"
                        : "未配置"
                      : "未启用"
                    : "不可用"}
                </span>
              </span>
            ))}
          </div>
          {result.search.warnings.length ? (
            <ul className="mt-2 space-y-1 text-amber-800">
              {result.search.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          <div className="mt-3 border-t border-slate-200 pt-2">
            <p className="font-medium text-slate-700">搜索诊断</p>
            <ul className="mt-1 space-y-1">
              {result.search.diagnostics
                .filter((item) => item.accepted === 0 || item.reason)
                .map((item) => (
                  <li key={item.company}>
                    <span className="font-medium">{formatCompany(item.company)}</span>：
                    {item.reason ?? "有候选"}
                    {item.raw_results ? `（原始 ${item.raw_results} 条` : "（"}
                    {`，列表/入口 ${item.dropped_list_or_landing}，过滤 ${item.dropped_filter}）`}
                  </li>
                ))}
            </ul>
          </div>
          <p className="mt-2 text-slate-500">
            发现窗口只表示本地发现/检索范围，不表示官网发布时间；官网日期仅在详情页提供时展示。
            点击“查看官网”会离开 CareerPilot，登录与申请均在官方站点完成。
          </p>
        </section>
      ) : null}

      {result ? (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            共 {result.total_jobs} 个已核验岗位 · {result.total_leads} 条候选链接
          </p>
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
            <button
              type="button"
              onClick={() => setView("cards")}
              aria-pressed={view === "cards"}
              className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs ${
                view === "cards" ? "bg-slate-900 text-white" : "text-slate-600"
              }`}
            >
              <LayoutGrid className="size-3.5" aria-hidden /> 卡片
            </button>
            <button
              type="button"
              onClick={() => setView("table")}
              aria-pressed={view === "table"}
              className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs ${
                view === "table" ? "bg-slate-900 text-white" : "text-slate-600"
              }`}
            >
              <Table2 className="size-3.5" aria-hidden /> 列表
            </button>
          </div>
        </div>
      ) : null}

      {result && result.jobs.length > 0 && view === "table" ? (
        <section className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">公司</th>
                <th className="px-3 py-2 font-medium">岗位</th>
                <th className="px-3 py-2 font-medium">城市</th>
                <th className="px-3 py-2 font-medium">类型</th>
                <th className="px-3 py-2 font-medium">来源</th>
                <th className="px-3 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {result.jobs.map((job) => (
                <tr key={job.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-700">{job.company}</td>
                  <td className="px-3 py-2 font-medium text-slate-900">{job.title}</td>
                  <td className="px-3 py-2 text-slate-600">{job.city ?? "未知"}</td>
                  <td className="px-3 py-2 text-slate-600">{job.job_type ?? "未知"}</td>
                  <td className="px-3 py-2 text-slate-600">已核验 JD</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <Link href={`/jobs/${job.id}`} className="text-sky-700 hover:underline">
                        详情
                      </Link>
                      <a
                        href={job.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-slate-600 hover:underline"
                      >
                        官网
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {result && result.jobs.length > 0 && view === "cards" ? (
        <section>
          <h2 className="text-sm font-semibold text-slate-900">已核验岗位</h2>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {result.jobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        </section>
      ) : null}

      {result ? (
        <section>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">候选岗位链接</h2>
            <span className="text-xs text-slate-500">未核验的链接不会伪装成完整 JD</span>
          </div>
          {result.leads.length === 0 ? (
            <p className="mt-3 rounded-lg border border-dashed border-slate-300 p-5 text-sm text-slate-500">
              没有候选链接。可以换关键词，或到“导入岗位”粘贴官方链接与 JD。
            </p>
          ) : (
            <div className="mt-3 space-y-3">
              {result.leads.map((lead) => (
                <article
                  key={lead.id}
                  className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill tone={verificationTone(lead.verification_status)}>
                      {lead.verification_status === "verified_official"
                        ? "官方 JD 已核验"
                        : lead.last_verification_error
                          ? "JD 获取失败"
                          : "仅搜索摘要"}
                    </StatusPill>
                    {lead.is_private ? (
                      <span className="text-[11px] text-slate-400">仅本人可见</span>
                    ) : null}
                    <span className="text-xs text-slate-500">{lead.company}</span>
                    <span className="text-[11px] text-slate-400">
                      {lead.source_kind === "trusted_ats"
                        ? "官方关联 ATS"
                        : lead.source_kind === "user_private"
                          ? "用户导入"
                          : "官网来源"}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {formatJobFamily(lead.job_family)}
                    </span>
                  </div>
                  <h3 className="mt-2 text-base font-semibold text-slate-900">
                    {lead.title}
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    {lead.published_date ? `官网日期：${lead.published_date}` : "官网日期未知"}
                    {" · "}
                    首次发现：{formatDateTime(lead.first_seen_at)}
                    {" · "}
                    最近核验：{lead.last_verified_at ? formatDateTime(lead.last_verified_at) : "未核验"}
                    {lead.last_verification_error
                      ? ` · 提取失败：${lead.last_verification_error}`
                      : ""}
                  </p>
                  {lead.summary ? (
                    <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-slate-600">
                      {lead.summary}
                    </p>
                  ) : null}
                  <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                    <a
                      href={lead.official_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 font-medium text-sky-700 hover:underline"
                    >
                      查看官网
                      <ArrowUpRight className="size-3" aria-hidden />
                    </a>
                    {lead.job_id ? (
                      <Link
                        href={`/jobs/${lead.job_id}`}
                        className="text-slate-700 hover:underline"
                      >
                        查看已核验岗位
                      </Link>
                    ) : lead.source_kind === "official" || lead.source_kind === "trusted_ats" ? (
                      <button
                        type="button"
                        onClick={() => verify(lead)}
                        disabled={pendingVerify === lead.id}
                        className="inline-flex items-center gap-1 text-slate-700 hover:text-slate-950 disabled:opacity-40"
                      >
                        <ShieldCheck className="size-3" aria-hidden />
                        {pendingVerify === lead.id ? "获取中..." : "获取详情并核验"}
                      </button>
                    ) : null}
                    <CreateApplicationButton
                      {...(lead.job_id ? { jobId: lead.job_id } : { leadId: lead.id })}
                      label="已申请，登记进度"
                    />
                  </div>
                </article>
              ))}
            </div>
          )}
          <div className="mt-4 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => runSearch(result.page - 1)}
              disabled={busy || result.page <= 1}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs disabled:opacity-40"
            >
              上一页
            </button>
            <span className="text-xs text-slate-500">
              第 {result.page} / {result.total_pages} 页
            </span>
            <button
              type="button"
              onClick={() => runSearch(result.page + 1)}
              disabled={busy || result.page >= result.total_pages}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
