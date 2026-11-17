import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { ArrowUpRight, Code2 } from "lucide-react";
import "./globals.css";

const base = process.env.NEXT_PUBLIC_SITE_BASE_PATH ?? "/CareerPilot";
export const metadata: Metadata = {
  metadataBase: new URL("https://lvsir18.github.io"),
  title: { default: "CareerPilot · 让求职每一步都有据可依", template: "%s · CareerPilot" },
  description: "面向国内实习与校招的个人求职工作台。了解官网岗位核验、可解释匹配、Agent 与投递跟进，免费阅读公开图文手册。",
  icons: { icon: `${base}/careerpilot-avatar.svg` },
};

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:p-3">跳到正文</a>
        <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/95 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4 sm:px-8">
            <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="CareerPilot 首页">
              <Image src={`${base}/careerpilot-avatar.svg`} width={30} height={30} alt="" unoptimized className="rounded-lg" />
              <span className="text-sm font-semibold tracking-tight">CareerPilot</span>
            </Link>
            <nav aria-label="站点导航" className="flex items-center gap-4 text-xs text-slate-600 sm:gap-6">
              <Link href="/guide/" className="hover:text-sky-700">用户手册</Link>
              <a href="https://github.com/lvsir18/CareerPilot" className="inline-flex items-center gap-1 hover:text-slate-950" aria-label="GitHub 仓库"><Code2 className="size-4" aria-hidden /><span className="hidden sm:inline">GitHub</span></a>
              <Link href="/start/" className="rounded-lg bg-slate-900 px-3 py-2 font-medium text-white hover:bg-slate-700">本地部署</Link>
            </nav>
          </div>
        </header>
        <main id="main">{children}</main>
        <footer className="border-t border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-8">
            <div><p className="font-medium text-slate-800">CareerPilot · 个人求职工作台</p><p className="mt-2 leading-6">MIT 开源 · 求职数据由自己管理 · 官方申请由本人完成</p></div>
            <div className="flex flex-wrap gap-5"><Link href="/guide/#limits" className="hover:text-sky-700">隐私与边界</Link><a href="https://github.com/lvsir18/CareerPilot/blob/main/LICENSE" className="hover:text-sky-700">MIT License</a><a href="https://github.com/lvsir18/CareerPilot/issues/new/choose" className="inline-flex items-center gap-1 hover:text-sky-700">反馈问题 <ArrowUpRight className="size-3" aria-hidden /></a></div>
          </div>
        </footer>
      </body>
    </html>
  );
}
