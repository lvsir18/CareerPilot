"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bot,
  Briefcase,
  CalendarDays,
  ClipboardList,
  Compass,
  FilePlus2,
  FileText,
  LayoutDashboard,
  LogOut,
  Settings,
  Sparkles,
  Star,
  UserRound,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { logout } from "@/lib/client-api";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  icon: ReactNode;
  href?: string;
  hint?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "概览", href: "/dashboard", icon: <LayoutDashboard className="size-4" aria-hidden /> },
  { label: "岗位库", href: "/jobs", icon: <Briefcase className="size-4" aria-hidden /> },
  {
    label: "发现岗位",
    href: "/discover",
    icon: <Compass className="size-4" aria-hidden />,
  },
  {
    label: "岗位推荐",
    href: "/matches",
    icon: <Sparkles className="size-4" aria-hidden />,
  },
  {
    label: "我的收藏",
    href: "/saved-jobs",
    icon: <Star className="size-4" aria-hidden />,
  },
  {
    label: "面试日程",
    href: "/calendar",
    icon: <CalendarDays className="size-4" aria-hidden />,
  },
  {
    label: "导入岗位",
    href: "/import",
    icon: <FilePlus2 className="size-4" aria-hidden />,
  },
  {
    label: "简历管理",
    href: "/resumes",
    icon: <FileText className="size-4" aria-hidden />,
  },
  {
    label: "我的画像",
    href: "/profile",
    icon: <UserRound className="size-4" aria-hidden />,
  },
  {
    label: "Agent 工作台",
    href: "/agent",
    icon: <Bot className="size-4" aria-hidden />,
  },
  {
    label: "投递看板",
    href: "/applications",
    icon: <ClipboardList className="size-4" aria-hidden />,
  },
  { label: "设置", icon: <Settings className="size-4" aria-hidden />, hint: "M6" },
];

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({
  children,
  userEmail,
}: {
  children: ReactNode;
  userEmail: string;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const current = NAV_ITEMS.find((item) => item.href && isActive(pathname, item.href));

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    const result = await logout();
    if (!result.ok) {
      setLogoutError(result.error.message);
      setLoggingOut(false);
      return;
    }
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-slate-50 lg:flex">
      <aside className="fixed inset-y-0 hidden w-64 flex-col border-r border-slate-800 bg-slate-950 lg:flex">
        <div className="flex items-center gap-3 px-5 py-5">
          <span className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold text-white shadow-lg shadow-sky-500/20">
            CP
          </span>
          <div>
            <p className="text-sm font-semibold text-white">CareerPilot</p>
            <p className="text-xs text-slate-400">智能求职 Agent</p>
          </div>
        </div>

        <nav aria-label="主导航" className="mt-2 flex-1 space-y-1 px-3">
          {NAV_ITEMS.map((item) =>
            item.href ? (
              <Link
                key={item.label}
                href={item.href}
                aria-current={
                  isActive(pathname, item.href) ? "page" : undefined
                }
                className={cn(
                  "flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive(pathname, item.href)
                    ? "bg-slate-800/80 font-medium text-white"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200",
                )}
              >
                <span className="flex items-center gap-2.5">
                  {item.icon}
                  {item.label}
                </span>
              </Link>
            ) : (
              <div
                key={item.label}
                aria-disabled="true"
                title={`${item.hint} 里程碑交付`}
                className="flex cursor-not-allowed items-center justify-between rounded-lg px-3 py-2 text-sm text-slate-500"
              >
                <span className="flex items-center gap-2.5">
                  {item.icon}
                  {item.label}
                </span>
                <span className="rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                  {item.hint}
                </span>
              </div>
            ),
          )}
        </nav>

        <div className="border-t border-slate-800 p-4">
          <div className="rounded-lg bg-slate-900 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">当前阶段</span>
              <span className="font-mono text-sky-300">M4</span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              简历解析、个人画像、可解释匹配与 LangGraph 多 Agent 工作流已可用。
            </p>
          </div>
          <div className="mt-3 flex items-center justify-between gap-2 px-1">
            <span className="truncate text-[11px] text-slate-500" title={userEmail}>
              {userEmail}
            </span>
            <button
              type="button"
              onClick={handleLogout}
              disabled={loggingOut}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-slate-400 transition-colors hover:bg-slate-800 hover:text-white disabled:opacity-50"
            >
              <LogOut className="size-3" aria-hidden />
              {loggingOut ? "退出中" : "退出"}
            </button>
          </div>
          {logoutError ? (
            <p className="mt-2 px-1 text-[11px] text-rose-400">{logoutError}</p>
          ) : null}
          <p className="mt-2 px-1 font-mono text-[11px] text-slate-600">v0.1.0 · dev baseline</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/85 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
            <div className="flex items-center gap-2 text-sm">
              <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-sky-400 to-indigo-500 text-[11px] font-bold text-white lg:hidden">
                CP
              </span>
              <span className="text-slate-400">CareerPilot</span>
              <span className="text-slate-300">/</span>
              <span className="font-medium text-slate-900">{current?.label ?? "概览"}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden max-w-[220px] truncate text-xs text-slate-500 sm:inline">
                {userEmail}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                disabled={loggingOut}
                className="rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 disabled:opacity-50 lg:hidden"
              >
                退出
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>

        <footer className="mx-auto w-full max-w-6xl px-4 pb-8 text-xs text-slate-400 sm:px-6">
          CareerPilot 不会自动向招聘网站提交申请；所有岗位都会保留可核验的原始来源。
        </footer>
      </div>
    </div>
  );
}
