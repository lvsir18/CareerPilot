import { JobDiscoveryPanel } from "@/components/job-discovery-panel";

export const dynamic = "force-dynamic";

export default function DiscoverPage() {
  return (
    <div className="space-y-6">
      <header className="border-b border-slate-200 pb-5">
        <p className="text-xs font-semibold tracking-[0.2em] text-sky-600 uppercase">
          M2-R1 · 站外发现
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">发现官方岗位</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
          搜索只覆盖已配置的官方招聘域名。搜索结果只是候选链接；只有成功读取官方详情页后，
          才会成为“官方已核验岗位”。搜索索引时间不等于官网发布时间。
        </p>
      </header>

      <JobDiscoveryPanel />
    </div>
  );
}
