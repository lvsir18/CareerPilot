import { redirect } from "next/navigation";
import { Bot, ShieldCheck, Briefcase } from "lucide-react";

import { LoginForm } from "@/components/login-form";
import { getCurrentUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const user = await getCurrentUser();
  if (user) {
    redirect("/dashboard");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
      <div className="grid w-full max-w-5xl gap-10 lg:grid-cols-2 lg:items-center">
        <section className="hidden text-slate-300 lg:block">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold text-white">
              CP
            </span>
            <div>
              <p className="text-lg font-semibold text-white">CareerPilot</p>
              <p className="text-sm text-slate-400">智能求职 Agent</p>
            </div>
          </div>

          <h2 className="mt-10 text-3xl font-semibold leading-snug tracking-tight text-white">
            岗位来源透明，
            <br />
            投递进度由你掌控。
          </h2>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400">
            从岗位发现到申请跟进，一个工作台完成：官方站点检索、简历解析画像、可解释匹配、
            申请进度登记，以及会调用真实数据的求职助手。
          </p>

          <ul className="mt-8 space-y-4 text-sm">
            <li className="flex items-start gap-3">
              <Briefcase className="mt-0.5 size-4 shrink-0 text-sky-400" aria-hidden />
              每条岗位保留来源类型、原始链接与可核验的发布时间
            </li>
            <li className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-sky-400" aria-hidden />
              用户数据严格隔离，密码使用 Argon2 哈希
            </li>
            <li className="flex items-start gap-3">
              <Bot className="mt-0.5 size-4 shrink-0 text-sky-400" aria-hidden />
              助手只调用真实岗位、画像与进度数据；不自动投递、不抓取受限信息
            </li>
          </ul>

          <p className="mt-10 font-mono text-xs text-slate-600">CareerPilot · v0.1.0</p>
        </section>

        <div className="flex justify-center">
          <LoginForm />
        </div>
      </div>
    </main>
  );
}
