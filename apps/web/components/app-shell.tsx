"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  Bot,
  Briefcase,
  CalendarDays,
  ClipboardList,
  Compass,
  FilePlus2,
  FileText,
  Home,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Settings,
  Sparkles,
  Star,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { getActivity, logout } from "@/lib/client-api";
import type { ActivitySnapshot } from "@/lib/api";
import { clearAllProfileDrafts } from "@/lib/profile-draft";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  icon: ReactNode;
  href?: string;
  hint?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "首页", href: "/home", icon: <Home className="size-4" aria-hidden /> },
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
  {
    label: "使用手册",
    href: "/guide",
    icon: <BookOpen className="size-4" aria-hidden />,
  },
  {
    label: "设置",
    href: "/settings/email",
    icon: <Settings className="size-4" aria-hidden />,
  },
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
  const isAgentWorkspace = pathname === "/agent";
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [activity, setActivity] = useState<ActivitySnapshot | null>(null);
  const current = NAV_ITEMS.find((item) => item.href && isActive(pathname, item.href));

  // Long tasks run in Celery, not in the page: poll so the sidebar keeps showing
  // a spinner after the user navigates away from 岗位库 / Agent 工作台.
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const result = await getActivity();
      if (!cancelled && result.ok) {
        setActivity(result.data);
      }
    }
    void poll();
    const timer = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  function isBusy(href: string | undefined): boolean {
    // Candidate verification belongs to 发现岗位, everything else to 岗位库.
    if (href === "/jobs") {
      const kind = activity?.job_maintenance?.kind;
      return Boolean(kind) && kind !== "verify_leads";
    }
    if (href === "/discover") {
      return activity?.job_maintenance?.kind === "verify_leads";
    }
    if (href === "/agent") {
      return Boolean(activity?.agent);
    }
    return false;
  }

  function renderNav(onNavigate?: () => void): ReactNode {
    return NAV_ITEMS.map((item) =>
      item.href ? (
        <Link
          key={item.label}
          href={item.href}
          onClick={onNavigate}
          aria-current={isActive(pathname, item.href) ? "page" : undefined}
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
          {isBusy(item.href) ? (
            <Loader2
              className="size-3.5 animate-spin text-sky-400"
              aria-label="后台任务运行中"
            />
          ) : null}
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
    );
  }

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    const result = await logout();
    if (!result.ok) {
      setLogoutError(result.error.message);
      setLoggingOut(false);
      return;
    }
    // Local drafts are per account; leaving them behind is what let the next
    // account on this browser see the previous user's unsaved edits.
    clearAllProfileDrafts();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className={cn("bg-slate-50 lg:flex", isAgentWorkspace ? "h-dvh overflow-hidden" : "min-h-screen")}>
      <aside className="fixed inset-y-0 hidden w-64 flex-col border-r border-slate-800 bg-slate-950 lg:flex">
        <div className="flex items-center gap-3 px-5 py-5">
          {/* eslint-disable-next-line @next/next/no-img-element -- local SVG logo */}
          <img
            src="/careerpilot-avatar.svg"
            alt="CareerPilot"
            width={36}
            height={36}
            className="size-9 rounded-xl shadow-lg shadow-sky-500/20"
          />
          <div>
            <p className="text-sm font-semibold text-white">CareerPilot</p>
            <p className="text-xs text-slate-400">智能求职 Agent</p>
          </div>
        </div>

        <nav aria-label="主导航" className="mt-2 flex-1 space-y-1 overflow-y-auto px-3">
          {renderNav()}
        </nav>

        <div className="border-t border-slate-800 p-4">
          <div className="rounded-lg bg-slate-900 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">使用建议</span>
              <span className="text-sky-300">3 步</span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              上传简历 → 核对并确认画像 → 查看推荐并登记投递进度。
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
        </div>
      </aside>

      {/* Mobile navigation: the desktop sidebar is hidden below lg, and without
          this drawer a phone user has no way to reach the rest of the app. */}
      {navOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="关闭导航菜单"
            onClick={() => setNavOpen(false)}
            className="absolute inset-0 h-full w-full bg-slate-900/50"
          />
          <nav
            aria-label="主导航"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col overflow-y-auto bg-slate-950 shadow-xl"
          >
            <div className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-3">
                {/* eslint-disable-next-line @next/next/no-img-element -- local SVG logo */}
                <img
                  src="/careerpilot-avatar.svg"
                  alt="CareerPilot"
                  width={36}
                  height={36}
                  className="size-9 rounded-xl"
                />
                <div>
                  <p className="text-sm font-semibold text-white">CareerPilot</p>
                  <p className="text-xs text-slate-400">智能求职 Agent</p>
                </div>
              </div>
              <button
                type="button"
                aria-label="关闭导航菜单"
                onClick={() => setNavOpen(false)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
            <div className="flex-1 space-y-1 px-3 pb-4">{renderNav(() => setNavOpen(false))}</div>
            <div className="border-t border-slate-800 px-5 py-3">
              <p className="truncate text-[11px] text-slate-500" title={userEmail}>
                {userEmail}
              </p>
              <button
                type="button"
                onClick={handleLogout}
                disabled={loggingOut}
                className="mt-2 inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-white disabled:opacity-50"
              >
                <LogOut className="size-3" aria-hidden />
                {loggingOut ? "退出中" : "退出"}
              </button>
            </div>
          </nav>
        </div>
      ) : null}

      <div className={cn("flex min-w-0 flex-1 flex-col lg:pl-64", isAgentWorkspace && "h-full min-h-0")}>
        <header className="sticky top-0 z-10 shrink-0 border-b border-slate-200 bg-white/85 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => setNavOpen(true)}
                aria-label="打开导航菜单"
                aria-expanded={navOpen}
                className="inline-flex size-8 items-center justify-center rounded-lg border border-slate-200 text-slate-600 lg:hidden"
              >
                <Menu className="size-4" aria-hidden />
              </button>
              {/* eslint-disable-next-line @next/next/no-img-element -- local SVG logo */}
              <img
                src="/careerpilot-avatar.svg"
                alt="CareerPilot"
                width={28}
                height={28}
                className="hidden size-7 rounded-lg sm:block lg:hidden"
              />
              <Link
                href="/home"
                className="hidden text-slate-400 transition-colors hover:text-slate-700 sm:inline"
              >
                CareerPilot
              </Link>
              <span className="hidden text-slate-300 sm:inline">/</span>
              <span className="truncate font-medium text-slate-900">
                {current?.label ?? "首页"}
              </span>
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

        {/* The chat needs a bounded flex ancestor for its internal scroll panes.
            Other pages retain normal document scrolling. */}
        <main className={cn(
          "mx-auto w-full max-w-6xl min-h-0 flex-1 px-4 sm:px-6",
          isAgentWorkspace ? "flex flex-col overflow-hidden py-4" : "py-6 sm:py-8",
        )}>
          {children}
        </main>

        <footer className={cn(
          "mx-auto w-full max-w-6xl shrink-0 px-4 text-xs text-slate-400 sm:px-6",
          isAgentWorkspace ? "pb-3" : "pb-8",
        )}>
          CareerPilot 不会自动向招聘网站提交申请；所有岗位都会保留可核验的原始来源。
        </footer>
      </div>
    </div>
  );
}
