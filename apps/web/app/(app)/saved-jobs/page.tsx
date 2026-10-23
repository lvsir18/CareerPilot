import { cookies } from "next/headers";
import Link from "next/link";
import { ArrowUpRight, Star } from "lucide-react";

import { StatusPill } from "@/components/status-pill";
import { fetchSavedJobs } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function SavedJobsPage() {
  const cookie = (await cookies()).toString();
  const result = await fetchSavedJobs(cookie, { list_type: "saved", page_size: 50 });

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">我的收藏</h1>
        <p className="mt-2 text-sm text-slate-600">
          收藏不改变申请状态；已失效岗位会保留并标注来源状态。
        </p>
      </section>

      {!result.ok ? (
        <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          收藏加载失败：{result.error.message}
        </p>
      ) : result.data.data.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          还没有收藏岗位。去 <Link href="/discover" className="text-sky-700 hover:underline">招聘信息</Link> 搜索并收藏。
        </p>
      ) : (
        <div className="space-y-3">
          {result.data.data.map((item) => (
            <article key={item.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-slate-900">
                    {item.job.company} · {item.job.title}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {item.job.city ?? "城市未知"} · {item.job.job_type ?? "类型未知"} · 收藏于{" "}
                    {formatDateTime(item.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill tone={item.job.verification_status === "verified" ? "ok" : "warning"}>
                    {item.job.verification_status === "verified" ? "已核验 JD" : "待核验"}
                  </StatusPill>
                  <a
                    href={item.job.source_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1 text-xs text-sky-700 hover:underline"
                  >
                    官网 <ArrowUpRight className="size-3" aria-hidden />
                  </a>
                  <Link
                    href={`/jobs/${item.job.id}`}
                    className="inline-flex items-center gap-1 text-xs text-slate-600 hover:underline"
                  >
                    <Star className="size-3" aria-hidden /> 详情
                  </Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
