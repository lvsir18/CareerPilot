"use client";

import { Mail, RefreshCw, Trash2, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import {
  connectQQMailbox,
  deleteMailbox,
  getGmailAuthorize,
  listMailboxes,
  listMailboxSyncRuns,
  syncMailbox,
  testMailbox,
  updateMailbox,
} from "@/lib/client-api";
import type { MailboxConnection, MailboxSyncRun } from "@/lib/api";
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
    </div>
  );
}
