"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { login, register } from "@/lib/client-api";

type Mode = "login" | "register";

export function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);

    const result =
      mode === "login" ? await login(email, password) : await register(email, password);

    if (!result.ok) {
      setError(result.error.message);
      setPending(false);
      return;
    }

    router.replace("/jobs");
    router.refresh();
  }

  return (
    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <div className="flex rounded-lg bg-slate-100 p-1 text-sm">
        {(["login", "register"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => {
              setMode(option);
              setError(null);
            }}
            className={
              mode === option
                ? "flex-1 rounded-md bg-white px-3 py-2 font-medium text-slate-900 shadow-sm"
                : "flex-1 rounded-md px-3 py-2 text-slate-500 hover:text-slate-700"
            }
          >
            {option === "login" ? "登录" : "注册"}
          </button>
        ))}
      </div>

      <h1 className="mt-6 text-xl font-semibold text-slate-900">
        {mode === "login" ? "登录 CareerPilot" : "创建你的账号"}
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        {mode === "login"
          ? "登录后可浏览岗位、收藏并记录投递进度。"
          : "注册即建立本地演示账号，无需任何外部凭据。"}
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
            密码
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={mode === "register" ? 8 : 1}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={mode === "register" ? "至少 8 个字符" : "输入密码"}
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

        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
        </button>
      </form>

      <p className="mt-5 text-xs leading-relaxed text-slate-500">
        演示模式：账号仅存储在本机 PostgreSQL，不会发送邮件；密码使用 Argon2
        哈希保存。所有岗位均标注来源，系统不会自动向招聘网站投递。
      </p>
    </div>
  );
}
