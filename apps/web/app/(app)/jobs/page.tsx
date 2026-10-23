import { cookies } from "next/headers";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Briefcase, CircleAlert, Search } from "lucide-react";

import { JobCard } from "@/components/job-card";
import { StatusPill } from "@/components/status-pill";
import { fetchJobs } from "@/lib/api";
import { jobPageHref, parseJobFilters, type JobFilters } from "@/lib/job-filters";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 12;

function hasFilters(filters: JobFilters): boolean {
  return Boolean(
    filters.q ||
      filters.cities ||
      filters.job_types ||
      filters.source_types ||
      filters.recruitment_program,
  );
}

export default async function JobsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filters = parseJobFilters(await searchParams);
  const cookie = (await cookies()).toString();
  const result = await fetchJobs(filters, cookie, PAGE_SIZE);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">岗位库</h1>
          <p className="mt-1 text-sm text-slate-600">
            所有岗位保留来源类型与原始链接；发布时间未知时不会推测为“最近发布”。
          </p>
        </div>
        <StatusPill tone="neutral">M1 · 只读岗位数据</StatusPill>
      </header>

      <form
        method="get"
        action="/jobs"
        className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5"
      >
        <div className="grid gap-3 lg:grid-cols-12">
          <div className="relative lg:col-span-4">
            <label htmlFor="q" className="sr-only">
              关键词
            </label>
            <Search
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400"
              aria-hidden
            />
            <input
              id="q"
              name="q"
              defaultValue={filters.q}
              placeholder="搜索岗位、公司或 JD 关键词"
              className="w-full rounded-lg border border-slate-300 py-2 pr-3 pl-9 text-sm outline-none transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            />
          </div>
          <div className="lg:col-span-2">
            <label htmlFor="cities" className="sr-only">
              城市
            </label>
            <input
              id="cities"
              name="cities"
              defaultValue={filters.cities}
              placeholder="城市，如 北京,上海"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            />
          </div>
          <div className="lg:col-span-2">
            <label htmlFor="recruitment_program" className="sr-only">
              招聘项目
            </label>
            <input
              id="recruitment_program"
              name="recruitment_program"
              defaultValue={filters.recruitment_program}
              placeholder="招聘项目，如 2027届秋招"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            />
          </div>
          <div className="lg:col-span-2">
            <label htmlFor="job_types" className="sr-only">
              岗位类型
            </label>
            <select
              id="job_types"
              name="job_types"
              defaultValue={filters.job_types}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            >
              <option value="">全部类型</option>
              <option value="internship">实习</option>
              <option value="campus">校招</option>
              <option value="full_time">全职</option>
            </select>
          </div>
          <div className="lg:col-span-2">
            <label htmlFor="sort" className="sr-only">
              排序
            </label>
            <select
              id="sort"
              name="sort"
              defaultValue={filters.sort}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
            >
              <option value="published_at_desc">按发布时间</option>
              <option value="first_seen_at_desc">按首次发现</option>
              <option value="title_asc">按名称</option>
            </select>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-slate-400">
            支持逗号分隔多值；搜索条件会保留在 URL 中，刷新或分享链接不丢失。
          </p>
          <div className="flex items-center gap-2">
            {hasFilters(filters) ? (
              <Link
                href="/jobs"
                className="rounded-lg px-3 py-2 text-sm text-slate-500 hover:bg-slate-50 hover:text-slate-800"
              >
                清空
              </Link>
            ) : null}
            <button
              type="submit"
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700"
            >
              搜索岗位
            </button>
          </div>
        </div>
      </form>

      {!result.ok ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6">
          <div className="flex items-center gap-2 text-sm font-medium text-rose-800">
            <CircleAlert className="size-4" aria-hidden />
            岗位加载失败
          </div>
          <p className="mt-2 text-sm text-rose-700">
            {result.error.message}（{result.error.code}）
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-600">
              共 <span className="font-medium text-slate-900">{result.data.meta.total}</span> 个岗位
              {result.data.meta.total > 0
                ? ` · 第 ${result.data.meta.page} / ${Math.max(
                    1,
                    Math.ceil(result.data.meta.total / result.data.meta.page_size),
                  )} 页`
                : ""}
            </p>
            {result.data.data.some((job) => job.is_demo) ? (
              <StatusPill tone="warning">当前结果包含演示数据，已逐条标记</StatusPill>
            ) : null}
          </div>

          {result.data.data.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
              <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
                <Briefcase className="size-5" aria-hidden />
              </div>
              <h2 className="mt-4 text-base font-semibold text-slate-900">没有匹配的岗位</h2>
              <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-slate-500">
                尝试减少筛选条件或更换关键词。若刚完成部署，可运行 <code>make seed</code>{" "}
                导入明确标注的演示岗位。
              </p>
              <Link
                href="/jobs"
                className="mt-4 inline-flex rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:border-slate-400"
              >
                清空筛选
              </Link>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {result.data.data.map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
          )}

          {result.data.meta.total > PAGE_SIZE ? (
            <nav aria-label="分页" className="flex items-center justify-between">
              {filters.page > 1 ? (
                <Link
                  href={jobPageHref(filters, filters.page - 1, PAGE_SIZE)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:border-slate-400"
                >
                  <ArrowLeft className="size-3.5" aria-hidden />
                  上一页
                </Link>
              ) : (
                <span />
              )}
              <span className="text-xs text-slate-400">
                第 {filters.page} 页
              </span>
              {filters.page * PAGE_SIZE < result.data.meta.total ? (
                <Link
                  href={jobPageHref(filters, filters.page + 1, PAGE_SIZE)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:border-slate-400"
                >
                  下一页
                  <ArrowRight className="size-3.5" aria-hidden />
                </Link>
              ) : (
                <span />
              )}
            </nav>
          ) : null}
        </>
      )}
    </div>
  );
}
