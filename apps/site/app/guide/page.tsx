import type { Metadata } from "next";
import { GuideReader } from "@/components/guide-reader";

export const metadata: Metadata = { title: "用户手册", alternates: { canonical: `${process.env.NEXT_PUBLIC_SITE_BASE_PATH ?? "/CareerPilot"}/guide/` } };
export default function PublicGuidePage() {
  return <div className="mx-auto max-w-7xl px-4 pb-12 pt-6 sm:px-8 sm:pt-8">
    <p className="mb-5 text-xs leading-6 text-slate-500">公开文档 · 无需注册或启动服务。功能入口在这里指向操作说明，完整工作台需自行部署。</p>
    <GuideReader publicSite assetPrefix={process.env.NEXT_PUBLIC_SITE_BASE_PATH ?? "/CareerPilot"} />
  </div>;
}
