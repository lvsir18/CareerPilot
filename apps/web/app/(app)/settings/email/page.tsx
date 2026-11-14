"use client";

import { Mail, RefreshCw, Trash2, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import {
  changePassword,
  clearLlmSettings,
  clearSearchSettings,
  connectQQMailbox,
  deleteMailbox,
  getGmailAuthorize,
  getLlmSettings,
  getSearchSettings,
  listMailboxes,
  listMailboxSyncRuns,
  saveLlmSettings,
  saveSearchSettings,
  syncMailbox,
  testLlmConnection,
  testMailbox,
  testSearchConnection,
  updateMailbox,
} from "@/lib/client-api";
import type {
  LlmSettings,
  MailboxConnection,
  MailboxSyncRun,
  SearchSettings,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const STATUS_LABEL: Record<string, string> = {
  active: "已连接",
  pending: "待授权",
  expired: "授权已失效",
  revoked: "已撤销",
  error: "连接异常",
};

export default function EmailSettingsPage() {
  const [mailboxes, setMailboxes] = useState<MailboxConnection[]>([]);
  const [runs, setRuns] = useState<Record<string, MailboxSyncRun[]>>({});
  const [email, setEmail] = useState("");
  const [authCode, setAuthCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [gmailMessage, setGmailMessage] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordNotice, setPasswordNotice] = useState<string | null>(null);
  const [llm, setLlm] = useState<LlmSettings | null>(null);
  const [llmProvider, setLlmProvider] = useState<"openai" | "anthropic">("openai");
  const [llmKey, setLlmKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmBusy, setLlmBusy] = useState(false);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmNotice, setLlmNotice] = useState<string | null>(null);
  const [llmTest, setLlmTest] = useState<string | null>(null);
  const [search, setSearch] = useState<SearchSettings | null>(null);
  const [searchKey, setSearchKey] = useState("");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchNotice, setSearchNotice] = useState<string | null>(null);
  const [searchTest, setSearchTest] = useState<string | null>(null);

  useEffect(() => {
    void loadLlm();
  }, []);

  async function loadLlm() {
    const result = await getLlmSettings();
    if (!result.ok) {
      return;
    }
    setLlm(result.data);
    if (result.data.provider) {
      setLlmProvider(result.data.provider);
    }
    setLlmBaseUrl(result.data.base_url ?? "");
    setLlmModel(result.data.model ?? "");
  }

  async function handleSaveLlm() {
    setLlmError(null);
    setLlmNotice(null);
    if (!llm?.key_set && !llmKey.trim()) {
      setLlmError("首次配置需要填写 API Key");
      return;
    }
    setLlmBusy(true);
    const result = await saveLlmSettings({
      provider: llmProvider,
      api_key: llmKey.trim() || undefined,
      base_url: llmBaseUrl.trim() || null,
      model: llmModel.trim() || null,
    });
    setLlmBusy(false);
    if (!result.ok) {
      setLlmError(result.error.message);
      return;
    }
    setLlm(result.data);
    setLlmKey("");
    setLlmNotice("已保存，仅对你自己的 Agent 任务生效。");
  }

  async function handleClearLlm() {
    setLlmBusy(true);
    setLlmError(null);
    setLlmNotice(null);
    const result = await clearLlmSettings();
    setLlmBusy(false);
    if (!result.ok) {
      setLlmError(result.error.message);
      return;
    }
    await loadLlm();
    setLlmKey("");
    setLlmNotice("已清除，将使用服务端默认 Key。");
  }

  useEffect(() => {
    void loadSearch();
  }, []);

  async function loadSearch() {
    const result = await getSearchSettings();
    if (result.ok) {
      setSearch(result.data);
    }
  }

  async function handleSaveSearch() {
    setSearchError(null);
    setSearchNotice(null);
    if (!search?.key_set && !searchKey.trim()) {
      setSearchError("首次配置需要填写 Tavily API Key");
      return;
    }
    setSearchBusy(true);
    const result = await saveSearchSettings(searchKey.trim());
    setSearchBusy(false);
    if (!result.ok) {
      setSearchError(result.error.message);
      return;
    }
    setSearch(result.data);
    setSearchKey("");
    setSearchNotice("已保存，仅对你自己的实时检索生效。");
  }

  async function handleClearSearch() {
    setSearchBusy(true);
    setSearchError(null);
    setSearchNotice(null);
    const result = await clearSearchSettings();
    setSearchBusy(false);
    if (!result.ok) {
      setSearchError(result.error.message);
      return;
    }
    await loadSearch();
    setSearchKey("");
    setSearchNotice("已清除，将不再使用你的 Key。");
  }

  async function handleTestLlm() {
    setLlmBusy(true);
    setLlmError(null);
    setLlmTest(null);
    const result = await testLlmConnection({
      provider: llmProvider,
      api_key: llmKey.trim() || undefined,
      base_url: llmBaseUrl.trim() || null,
      model: llmModel.trim() || null,
    });
    setLlmBusy(false);
    if (!result.ok) {
      setLlmError(result.error.message);
      return;
    }
    setLlmTest(`连接成功 · ${result.data.latency_ms}ms · ${result.data.target}`);
  }

  async function handleTestSearch() {
    setSearchBusy(true);
    setSearchError(null);
    setSearchTest(null);
    const result = await testSearchConnection(searchKey.trim() || undefined);
    setSearchBusy(false);
    if (!result.ok) {
      setSearchError(result.error.message);
      return;
    }
    setSearchTest(`连接成功 · ${result.data.latency_ms}ms · ${result.data.target}`);
  }

  async function handleChangePassword() {
    setPasswordError(null);
    setPasswordNotice(null);
    if (newPassword.length < 8) {
      setPasswordError("新密码至少 8 个字符");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("两次输入的新密码不一致");
      return;
    }
    setPasswordBusy(true);
    const result = await changePassword(currentPassword, newPassword);
    setPasswordBusy(false);
    if (!result.ok) {
      setPasswordError(result.error.message);
      return;
    }
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setPasswordNotice("密码已更新，其他设备上的登录会话已失效。");
  }

  async function refresh() {
    const result = await listMailboxes();
    if (result.ok) setMailboxes(result.data);
    else setError(result.error.message);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void refresh();
  }, []);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- read OAuth result from URL once */
    const params = new URLSearchParams(window.location.search);
    const gmail = params.get("gmail");
    if (gmail === "connected") setNotice("Gmail 授权成功，可以立即同步或等待定时同步。");
    else if (gmail === "error") setError("Gmail 授权失败或已取消，请重试。");
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  async function handleConnectQQ() {
    if (!email.trim() || authCode.trim().length < 4) {
      setError("请填写邮箱地址和 QQ 授权码");
      return;
    }
    setBusy(true);
    setError(null);
    const result = await connectQQMailbox({
      email_address: email.trim(),
      auth_code: authCode.trim(),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setEmail("");
    setAuthCode("");
    setNotice("QQ 邮箱连接成功，可立即同步或等待定时同步。");
    await refresh();
  }

  async function handleGmail() {
    const result = await getGmailAuthorize();
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    if (!result.data.configured || !result.data.authorize_url) {
      setGmailMessage(result.data.message);
      return;
    }
    window.location.href = result.data.authorize_url;
  }

  async function handleSync(id: string) {
    setBusy(true);
    setError(null);
    const result = await syncMailbox(id);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setNotice(
      `同步完成：扫描 ${result.data.scanned_count} 封，新增候选 ${result.data.candidate_count}，` +
        `重复 ${result.data.duplicate_count}，错误 ${result.data.error_count}`,
    );
    await refresh();
    const runsResult = await listMailboxSyncRuns(id);
    if (runsResult.ok) setRuns((prev) => ({ ...prev, [id]: runsResult.data }));
  }

  async function handleTest(id: string) {
    const result = await testMailbox(id);
    if (!result.ok) setError(result.error.message);
    else {
      setNotice("连接测试通过");
      await refresh();
    }
  }

  async function handleToggle(mailbox: MailboxConnection) {
    await updateMailbox(mailbox.id, { sync_enabled: !mailbox.sync_enabled });
    await refresh();
  }

  async function handleDelete(id: string) {
    const result = await deleteMailbox(id);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setNotice(result.data.message);
    await refresh();
  }

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">邮箱同步</h1>
        <p className="mt-2 text-sm text-slate-600">
          绑定个人邮箱后，系统只读取招聘相关邮件并生成“待确认”进度建议；确认前不会修改申请状态。
          邮件同步不等于企业官网同步。
        </p>
      </section>

      {error ? (
        <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>
      ) : null}
      {notice ? (
        <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          {notice}
        </p>
      ) : null}

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">绑定 QQ 邮箱</h2>
        <p className="mt-1 text-xs text-slate-500">
          需在 QQ 邮箱设置中开启 IMAP 并生成“授权码”（不是登录密码）。仅使用 imap.qq.com:993 只读访问。
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@qq.com"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            value={authCode}
            onChange={(event) => setAuthCode(event.target.value)}
            placeholder="授权码"
            type="password"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => void handleConnectQQ()}
            disabled={busy}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            绑定并测试连接
          </button>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">
          授权码使用服务端加密存储；未配置 MAILBOX_SECRET_KEY 时不会保存凭据。
        </p>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">绑定 Gmail</h2>
        <p className="mt-1 text-xs text-slate-500">
          使用 Google OAuth 只读权限（gmail.readonly），不申请发送或修改权限。
        </p>
        <button
          type="button"
          onClick={() => void handleGmail()}
          className="mt-3 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
        >
          使用 Google 授权
        </button>
        {gmailMessage ? (
          <p className="mt-2 flex items-center gap-1 text-xs text-amber-700">
            <ShieldAlert className="size-3.5" aria-hidden />
            {gmailMessage}
          </p>
        ) : null}
      </section>

      <section className="space-y-3">
        {mailboxes.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
            尚未绑定邮箱
          </p>
        ) : (
          mailboxes.map((mailbox) => (
            <article key={mailbox.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="flex items-center gap-2 text-sm font-medium text-slate-900">
                    <Mail className="size-4 text-slate-400" aria-hidden />
                    {mailbox.email_address}
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
                      {mailbox.provider === "qq_imap" ? "QQ 邮箱" : "Gmail"}
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {STATUS_LABEL[mailbox.status] ?? mailbox.status} · 最近成功同步：
                    {mailbox.last_success_at ? formatDateTime(mailbox.last_success_at) : "从未"}
                    {mailbox.sync_enabled ? " · 自动同步已开启" : " · 自动同步已暂停"}
                  </p>
                  {mailbox.last_error ? (
                    <p className="mt-1 text-xs text-rose-600">{mailbox.last_error}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => void handleTest(mailbox.id)}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700"
                  >
                    测试连接
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleSync(mailbox.id)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 rounded-lg bg-sky-600 px-3 py-1.5 text-white disabled:opacity-40"
                  >
                    <RefreshCw className="size-3.5" aria-hidden /> 立即同步
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleToggle(mailbox)}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700"
                  >
                    {mailbox.sync_enabled ? "暂停自动同步" : "开启自动同步"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(mailbox.id)}
                    className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-rose-600"
                  >
                    <Trash2 className="size-3.5" aria-hidden /> 解绑
                  </button>
                </div>
              </div>

              {runs[mailbox.id]?.length ? (
                <ul className="mt-3 divide-y divide-slate-100 text-xs">
                  {runs[mailbox.id]?.slice(0, 5).map((run) => (
                    <li key={run.id} className="flex flex-wrap gap-3 py-1.5 text-slate-600">
                      <span>{formatDateTime(run.started_at)}</span>
                      <span>{run.status}</span>
                      <span>扫描 {run.scanned_count}</span>
                      <span>候选 {run.candidate_count}</span>
                      <span>重复 {run.duplicate_count}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">账号安全</h2>
        <p className="mt-1 text-xs text-slate-500">
          修改登录密码。当前浏览器会保持登录，其他设备上的会话会立即失效。
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            placeholder="当前密码"
            autoComplete="current-password"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            placeholder="新密码（至少 8 位）"
            autoComplete="new-password"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            placeholder="再次输入新密码"
            autoComplete="new-password"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleChangePassword()}
            disabled={passwordBusy}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {passwordBusy ? "更新中…" : "更新密码"}
          </button>
          {passwordError ? (
            <span className="text-xs text-rose-700">{passwordError}</span>
          ) : null}
          {passwordNotice ? (
            <span className="text-xs text-emerald-700">{passwordNotice}</span>
          ) : null}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">模型 API</h2>
          <span
            className={
              llm?.configured
                ? "rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                : "rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600"
            }
          >
            {llm?.configured
              ? `使用自己的 Key · ${llm.masked_key ?? "已保存"}`
              : llm?.server_default_available
                ? "当前使用服务端默认 Key"
                : "尚未配置模型"}
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          不配置时使用服务端默认 Key；配置后只影响你自己的 Agent 任务。Key 加密存储、不会回显，
          也不会出现在日志里。支持 OpenAI 兼容接口（可填自建/第三方网关）与 Anthropic 官方接口。
        </p>

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-600">
            提供方
            <select
              value={llmProvider}
              onChange={(event) => setLlmProvider(event.target.value as "openai" | "anthropic")}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="openai">OpenAI 兼容（OpenAI / DeepSeek / 自建网关）</option>
              <option value="anthropic">Anthropic（Claude 官方）</option>
            </select>
          </label>
          <label className="text-xs text-slate-600">
            API Key
            <input
              type="password"
              value={llmKey}
              onChange={(event) => setLlmKey(event.target.value)}
              placeholder={llm?.key_set ? "已保存，留空表示不修改" : "粘贴你的 API Key"}
              autoComplete="off"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-slate-600">
            Base URL（可选）
            <input
              value={llmBaseUrl}
              onChange={(event) => setLlmBaseUrl(event.target.value)}
              placeholder={
                llmProvider === "openai"
                  ? "https://api.openai.com/v1 或你的兼容网关"
                  : "默认使用 Anthropic 官方地址"
              }
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-slate-600">
            模型（可选）
            <input
              value={llmModel}
              onChange={(event) => setLlmModel(event.target.value)}
              placeholder={
                llmProvider === "openai" ? "如 gpt-4o-mini / deepseek-chat" : "如 claude-3-5-sonnet-latest"
              }
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleSaveLlm()}
            disabled={llmBusy}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {llmBusy ? "保存中…" : "保存"}
          </button>
          <button
            type="button"
            onClick={() => void handleTestLlm()}
            disabled={llmBusy}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-40"
          >
            测试连接
          </button>
          {llm?.configured ? (
            <button
              type="button"
              onClick={() => void handleClearLlm()}
              disabled={llmBusy}
              className="text-xs text-rose-600 hover:underline disabled:opacity-40"
            >
              清除，改用服务端默认
            </button>
          ) : null}
          {llmError ? <span className="text-xs text-rose-700">{llmError}</span> : null}
          {llmNotice ? <span className="text-xs text-emerald-700">{llmNotice}</span> : null}
          {llmTest ? <span className="text-xs text-emerald-700">{llmTest}</span> : null}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">搜索 API（Tavily）</h2>
          <span
            className={
              search?.configured
                ? "rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                : "rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600"
            }
          >
            {search?.configured
              ? `使用自己的 Key · ${search.masked_key ?? "已保存"}`
              : search?.server_default_available && !search.server_default_admins_only
                ? "当前使用服务端默认 Key"
                : search?.server_default_available
                  ? "未配置（服务端 Key 仅限管理员）"
                  : "未配置"}
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          实时检索会消耗 Tavily credits。未配置时：管理员沿用服务端默认 Key，其他账号只查岗位库、
          不发实时检索请求，避免共用部署者的额度。Key 加密存储、只显示掩码。
        </p>

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-600">
            Tavily API Key
            <input
              type="password"
              value={searchKey}
              onChange={(event) => setSearchKey(event.target.value)}
              placeholder={search?.key_set ? "已保存，留空表示不修改" : "tvly-..."}
              autoComplete="off"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleSaveSearch()}
            disabled={searchBusy}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {searchBusy ? "保存中…" : "保存"}
          </button>
          <button
            type="button"
            onClick={() => void handleTestSearch()}
            disabled={searchBusy}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-40"
          >
            测试连接
          </button>
          {search?.configured ? (
            <button
              type="button"
              onClick={() => void handleClearSearch()}
              disabled={searchBusy}
              className="text-xs text-rose-600 hover:underline disabled:opacity-40"
            >
              清除我的 Key
            </button>
          ) : null}
          {searchError ? <span className="text-xs text-rose-700">{searchError}</span> : null}
          {searchNotice ? <span className="text-xs text-emerald-700">{searchNotice}</span> : null}
          {searchTest ? <span className="text-xs text-emerald-700">{searchTest}</span> : null}
        </div>
      </section>
    </div>
  );
}
