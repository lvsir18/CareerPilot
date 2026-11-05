"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { login, register, resetPassword } from "@/lib/client-api";

type Mode = "login" | "register" | "reset";

const TAB_LABEL: Record<"login" | "register", string> = {
  login: "登录",
  register: "注册",
};

export function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setNotice(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setPending(true);

    const result =
      mode === "login"
        ? await login(email, password)
        : mode === "register"
          ? await register(email, password)
          : await resetPassword(email, password);

    if (!result.ok) {
      setError(result.error.message);
      setPending(false);
      return;
    }

    if (mode === "reset") {
      // Reset does not create a session: send the user back to login.
      setMode("login");
      setPassword("");
      setPending(false);
      setNotice("密码已重置，请用新密码登录。");
      return;
    }

    router.replace("/jobs");
    router.refresh();
  }

  const needsStrongPassword = mode === "register" || mode === "reset";

  return (
    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <div className="flex rounded-lg bg-slate-100 p-1 text-sm">
        {(["login", "register"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => switchMode(option)}
            className={
              mode === option
                ? "flex-1 rounded-md bg-white px-3 py-2 font-medium text-slate-900 shadow-sm"
                : "flex-1 rounded-md px-3 py-2 text-slate-500 hover:text-slate-700"
            }
          >
            {TAB_LABEL[option]}
          </button>
        ))}
      </div>

      <h1 className="mt-6 text-xl font-semibold text-slate-900">
        {mode === "login"
          ? "登录 CareerPilot"
          : mode === "register"
            ? "创建你的账号"
            : "重置密码"}
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        {mode === "login"
          ? "登录后可浏览岗位、收藏并记录投递进度。"
          : mode === "register"
            ? "注册即建立本地演示账号，无需任何外部凭据。"
            : "输入注册邮箱和新的密码即可重置（仅在部署开启重置时可用）。"}
      </p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div>
          <label htmlFor="email" className="text-sm font-medium text-slate-700">
            邮箱
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          />
        </div>

        <div>
          <label htmlFor="password" className="text-sm font-medium text-slate-700">
            {mode === "reset" ? "新密码" : "密码"}
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={needsStrongPassword ? 8 : 1}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={needsStrongPassword ? "至少 8 个字符" : "输入密码"}
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          />
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
          >
            {error}
          </p>
        ) : null}

        {notice ? (
          <p
            role="status"
            className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
          >
            {notice}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending
            ? "处理中…"
            : mode === "login"
              ? "登录"
              : mode === "register"
                ? "注册并登录"
                : "重置密码"}
        </button>
      </form>

      <div className="mt-4 flex items-center justify-between text-xs">
        {mode === "reset" ? (
          <button
            type="button"
            onClick={() => switchMode("login")}
            className="text-sky-700 hover:underline"
          >
            返回登录
          </button>
        ) : (
          <button
            type="button"
            onClick={() => switchMode("reset")}
            className="text-slate-500 hover:text-slate-700 hover:underline"
          >
            忘记密码？
          </button>
        )}
        <span className="text-slate-400">密码以 Argon2 哈希保存</span>
      </div>

      <p className="mt-4 text-xs leading-relaxed text-slate-500">
        演示模式：账号仅存储在本机 PostgreSQL，不会发送邮件；密码使用 Argon2
        哈希保存。所有岗位均标注来源，系统不会自动向招聘网站投递。
      </p>
    </div>
  );
}
