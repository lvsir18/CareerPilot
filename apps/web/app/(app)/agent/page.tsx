"use client";

import { Bot, Pencil, Plus, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { AgentMessageBubble } from "@/components/agent-message";
import {
  cancelAgentRun,
  createAgentRun,
  createAgentThread,
  deleteAgentThread,
  getAgentRun,
  listAgentMessages,
  listAgentThreads,
  renameAgentThread,
  resumeAgent,
} from "@/lib/client-api";
import type {
  AgentMessage,
  AgentRun,
  AgentRunEventItem,
  AgentRunResult,
  AgentThread,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "帮我找北京的大模型实习",
  "哪些岗位更适合我的简历？",
  "看看我最近的申请进度",
];

function syncThreadUrl(threadId: string | null) {
  if (typeof window === "undefined") {
    return;
  }
  window.history.replaceState(
    null,
    "",
    threadId ? `/agent?thread=${encodeURIComponent(threadId)}` : "/agent",
  );
}

export default function AgentPage() {
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [current, setCurrent] = useState<AgentThread | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [input, setInput] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("q") ?? "";
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [structured, setStructured] = useState<AgentRunResult["structured"]>(null);
  // Async execution state: the run is created immediately, then followed via SSE.
  const [run, setRun] = useState<AgentRun | null>(null);
  const [steps, setSteps] = useState<AgentRunEventItem[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  const loadToken = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshThreads = useCallback(async () => {
    const result = await listAgentThreads();
    if (!result.ok) {
      return;
    }
    setThreads(result.data);
    setCurrent((prev) => (prev ? (result.data.find((t) => t.id === prev.id) ?? prev) : prev));
  }, []);

  const openThread = useCallback(async (thread: AgentThread) => {
    const token = loadToken.current + 1;
    loadToken.current = token;
    setCurrent(thread);
    setError(null);
    setStructured(null);
    setRun(null);
    setSteps([]);
    setMessages([]);
    setLoadingMessages(true);
    syncThreadUrl(thread.id);
    const result = await listAgentMessages(thread.id);
    if (loadToken.current !== token) {
      return;
    }
    setMessages(result.ok ? result.data : []);
    if (!result.ok) {
      setError(result.error.message);
    }
    setLoadingMessages(false);
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await listAgentThreads();
      if (!active) {
        return;
      }
      if (!result.ok) {
        setError(result.error.message);
        return;
      }
      setThreads(result.data);
      const requested = new URLSearchParams(window.location.search).get("thread");
      const target = result.data.find((item) => item.id === requested) ?? result.data[0];
      if (target) {
        await openThread(target);
      }
    })();
    return () => {
      active = false;
    };
  }, [openThread]);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, loadingMessages, busy]);

  async function newThread() {
    const result = await createAgentThread();
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setThreads((prev) => [result.data, ...prev]);
    setCurrent(result.data);
    setMessages([]);
    setStructured(null);
    setRun(null);
    setSteps([]);
    setError(null);
    syncThreadUrl(result.data.id);
  }

  function startRename(thread: AgentThread) {
    setEditingId(thread.id);
    setDraftTitle(thread.title);
  }

  function cancelRename() {
    setEditingId(null);
  }

  async function commitRename(thread: AgentThread) {
    const title = draftTitle.trim();
    setEditingId(null);
    if (!title || title === thread.title) {
      return;
    }
    const result = await renameAgentThread(thread.id, title);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setThreads((prev) => prev.map((item) => (item.id === result.data.id ? result.data : item)));
    setCurrent((prev) => (prev && prev.id === result.data.id ? result.data : prev));
  }

  async function removeThread(thread: AgentThread) {
    const confirmed = window.confirm(
      `确定删除会话「${thread.title}」？\n\n该会话的消息与运行记录会一并删除，且无法恢复。`,
    );
    if (!confirmed) {
      return;
    }
    const result = await deleteAgentThread(thread.id);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setThreads((prev) => prev.filter((item) => item.id !== thread.id));
    if (editingId === thread.id) {
      cancelRename();
    }
    if (current?.id === thread.id) {
      setCurrent(null);
      setMessages([]);
      setSteps([]);
      setStructured(null);
      setRun(null);
      syncThreadUrl(null);
    }
    void refreshThreads();
  }

  function applyFinal(data: AgentRunResult | null, status: string) {
    setBusy(false);
    if (!data) return;
    if (data.final_answer) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.final_answer ?? "" },
      ]);
    }
    setStructured(data.structured ?? null);
    if (status === "waiting_for_user") {
      setError("需要你先确认画像：请前往 /profile 确认后再继续。");
    }
  }

  function followRun(runId: string) {
    const types = [
      "run.queued",
      "run.started",
      "plan.created",
      "agent.started",
      "tool.started",
      "tool.completed",
      "agent.completed",
      "run.completed",
      "run.partial",
      "run.failed",
      "run.cancelled",
      "approval.required",
      "run.final",
    ];
    let closed = false;
    const source = new EventSource(`/api/v1/agent/runs/${runId}/stream`);

    const finish = (status: string, result: AgentRunResult | null) => {
      if (closed) return;
      closed = true;
      source.close();
      applyFinal(result, status);
      void refreshThreads();
    };

    for (const type of types) {
      source.addEventListener(type, (event) => {
        const parsed = JSON.parse((event as MessageEvent<string>).data) as {
          sequence: number;
          event_type: string;
          payload: Record<string, unknown>;
          status?: string;
          result?: AgentRunResult;
        };
        setSteps((prev) =>
          prev.some((item) => item.sequence === parsed.sequence)
            ? prev
            : [
                ...prev,
                {
                  sequence: parsed.sequence,
                  event_type: parsed.event_type ?? type,
                  safe_payload: parsed.payload ?? {},
                  created_at: new Date().toISOString(),
                },
              ],
        );
        if (type === "run.final") {
          finish(String(parsed.status ?? "completed"), parsed.result ?? null);
        } else if (type.startsWith("run.") || type === "approval.required") {
          finish(type.replace("run.", ""), null);
        }
      });
    }

    // Fallback: if SSE never connects, poll the run status instead.
    source.onerror = () => {
      if (closed) return;
      source.close();
      closed = true;
      void pollRun(runId);
    };
  }

  async function pollRun(runId: string) {
    for (let i = 0; i < 120; i += 1) {
      const result = await getAgentRun(runId);
      if (!result.ok) {
        setBusy(false);
        return;
      }
      setRun(result.data);
      if (
        ["completed", "partial", "failed", "cancelled", "timed_out"].includes(
          result.data.status,
        )
      ) {
        applyFinal(result.data.result, result.data.status);
        void refreshThreads();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    setBusy(false);
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;

    let thread = current;
    if (!thread) {
      const created = await createAgentThread();
      if (!created.ok) {
        setError(created.error.message);
        return;
      }
      thread = created.data;
      setThreads((prev) => [created.data, ...prev]);
      setCurrent(created.data);
      syncThreadUrl(created.data.id);
    }

    setBusy(true);
    setError(null);
    setSteps([]);
    const userMessage: AgentMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    // Mirror the backend auto-title immediately so the sidebar stops showing
    // "新对话" while the first run is still queued.
    const threadId = thread.id;
    if (thread.title === "新对话") {
      const nextTitle = text.length > 30 ? `${text.slice(0, 30)}…` : text;
      setThreads((prev) =>
        prev.map((item) => (item.id === threadId ? { ...item, title: nextTitle } : item)),
      );
      setCurrent((prev) => (prev && prev.id === threadId ? { ...prev, title: nextTitle } : prev));
    }
    const result = await createAgentRun({
      thread_id: thread.id,
      request_id:
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `req-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      message: userMessage.content,
    });
    if (!result.ok) {
      setBusy(false);
      setError(result.error.message);
      return;
    }
    setRun(result.data);
    followRun(result.data.id);
  }

  async function cancel() {
    if (!run) return;
    const result = await cancelAgentRun(run.id);
    if (result.ok) setRun(result.data);
  }

  async function resume() {
    if (!current) return;
    setBusy(true);
    const result = await resumeAgent(current.id, true);
    setBusy(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    if (result.data.final_answer) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.data.final_answer ?? "" },
      ]);
    }
    setStructured(result.data.structured ?? null);
  }

  function renderTitleEditor(thread: AgentThread, className: string) {
    return (
      <input
        autoFocus
        value={draftTitle}
        aria-label="会话名称"
        title="回车保存，Esc 取消"
        onChange={(event) => setDraftTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void commitRename(thread);
          } else if (event.key === "Escape") {
            event.preventDefault();
            cancelRename();
          }
        }}
        className={cn(
          "min-w-0 rounded border border-sky-400 px-2 py-1 text-xs outline-none",
          className,
        )}
      />
    );
  }

  return (
    <div className="flex h-[calc(100vh-6rem)] gap-4">
      <aside className="flex w-60 shrink-0 flex-col rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <button
          type="button"
          onClick={() => void newThread()}
          className="flex w-full items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white"
        >
          <Plus className="size-4" aria-hidden />
          新建对话
        </button>
        <div className="mt-3 flex-1 space-y-1 overflow-y-auto">
          {threads.length === 0 ? (
            <p className="px-2 py-3 text-[11px] text-slate-400">还没有对话记录</p>
          ) : (
            threads.map((thread) => (
              <div
                key={thread.id}
                className={cn(
                  "group flex items-center rounded-lg pr-1",
                  current?.id === thread.id ? "bg-sky-50" : "hover:bg-slate-50",
                )}
              >
                {editingId === thread.id ? (
                  renderTitleEditor(thread, "m-1 flex-1")
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => void openThread(thread)}
                      title={thread.title}
                      className={cn(
                        "min-w-0 flex-1 truncate px-3 py-2 text-left text-xs",
                        current?.id === thread.id ? "text-sky-700" : "text-slate-600",
                      )}
                    >
                      {thread.title}
                    </button>
                    <button
                      type="button"
                      onClick={() => startRename(thread)}
                      aria-label={`重命名会话：${thread.title}`}
                      title="重命名"
                      className="rounded p-1 text-slate-400 opacity-0 transition-opacity group-hover:opacity-100 hover:text-slate-700 focus-visible:opacity-100"
                    >
                      <Pencil className="size-3" aria-hidden />
                    </button>
                    <button
                      type="button"
                      onClick={() => void removeThread(thread)}
                      aria-label={`删除会话：${thread.title}`}
                      title="删除会话"
                      className="rounded p-1 text-slate-400 opacity-0 transition-opacity group-hover:opacity-100 hover:text-rose-600 focus-visible:opacity-100"
                    >
                      <Trash2 className="size-3" aria-hidden />
                    </button>
                  </>
                )}
              </div>
            ))
          )}
        </div>
      </aside>

      <section className="flex flex-1 flex-col rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
          <Bot className="size-4 text-slate-400" aria-hidden />
          {current ? (
            editingId === current.id ? (
              renderTitleEditor(current, "w-64")
            ) : (
              <>
                <span className="max-w-[24rem] truncate text-sm font-medium text-slate-700">
                  {current.title}
                </span>
                <button
                  type="button"
                  onClick={() => startRename(current)}
                  aria-label="重命名当前会话"
                  title="重命名"
                  className="rounded p-1 text-slate-400 hover:text-slate-700"
                >
                  <Pencil className="size-3" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => void removeThread(current)}
                  aria-label="删除当前会话"
                  title="删除会话"
                  className="rounded p-1 text-slate-400 hover:text-rose-600"
                >
                  <Trash2 className="size-3" aria-hidden />
                </button>
              </>
            )
          ) : (
            <span className="text-sm font-medium text-slate-700">智能求职助手</span>
          )}
          <Link href="/discover" className="ml-auto text-xs text-sky-700 hover:underline">
            在招聘中心查看
          </Link>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
          <div className="mx-auto w-full max-w-2xl space-y-3">
            {loadingMessages ? (
              <p className="text-sm text-slate-500">正在加载会话…</p>
            ) : messages.length === 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-500">
                  {current
                    ? "问我「帮我找字节和小红书的大模型实习」或「哪些岗位更适合我的简历」。"
                    : "从左侧选择一个历史对话，或直接输入需求开始新对话。"}
                </p>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => setInput(suggestion)}
                      className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:border-sky-400 hover:text-sky-700"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages
                .filter((message) => message.role === "user" || message.role === "assistant")
                .map((message, index) => (
                  <AgentMessageBubble key={index} message={message} />
                ))
            )}
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}

            {structured &&
            (structured.jobs?.length || structured.matches?.length || structured.applications?.length) ? (
              <div className="space-y-2">
                {structured.jobs?.slice(0, 6).map((job, index) => (
                  <div key={`job-${job.id ?? index}`} className="rounded-lg border border-slate-200 bg-white p-3">
                    <p className="text-sm font-medium text-slate-800">
                      {job.company ?? "未知企业"} · {job.title ?? "未知岗位"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {job.city ?? "城市未知"} · {job.job_type ?? "类型未知"}
                      {job.verification_status === "verified" ? " · 已核验 JD" : " · 待核验摘要"}
                    </p>
                    <div className="mt-1 flex gap-3 text-xs">
                      {job.source_url || job.official_url ? (
                        <a
                          href={job.source_url ?? job.official_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-sky-700 hover:underline"
                        >
                          官网
                        </a>
                      ) : null}
                      {job.id ? (
                        <Link href={`/jobs/${job.id}`} className="text-slate-600 hover:underline">
                          详情
                        </Link>
                      ) : null}
                      <Link href={`/discover?q=${encodeURIComponent(job.title ?? "")}`} className="text-slate-600 hover:underline">
                        在招聘中心查看
                      </Link>
                    </div>
                  </div>
                ))}

                {structured.matches?.slice(0, 6).map((item, index) => (
                  <div key={`match-${item.job?.id ?? index}`} className="rounded-lg border border-slate-200 bg-white p-3">
                    <p className="text-sm font-medium text-slate-800">
                      {item.job?.company ?? "未知企业"} · {item.job?.title ?? "未知岗位"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      匹配 {item.match?.match_score != null ? `${item.match.match_score}/100` : "信息不足"} ·{" "}
                      {item.match?.eligibility_status ?? "unknown"}
                    </p>
                    {item.match?.matched_skills?.length ? (
                      <p className="mt-1 text-xs text-emerald-700">
                        命中：{item.match.matched_skills.join("、")}
                      </p>
                    ) : null}
                    {item.match?.unverified_skills?.length ? (
                      <p className="mt-0.5 text-xs text-slate-500">
                        未体现：{item.match.unverified_skills.join("、")}
                      </p>
                    ) : null}
                    <div className="mt-1 flex gap-3 text-xs">
                      {item.job?.id ? (
                        <Link href={`/jobs/${item.job.id}`} className="text-sky-700 hover:underline">
                          详情
                        </Link>
                      ) : null}
                      {item.job?.source_url ? (
                        <a href={item.job.source_url} target="_blank" rel="noreferrer noopener" className="text-slate-600 hover:underline">
                          官网
                        </a>
                      ) : null}
                    </div>
                  </div>
                ))}

                {structured.applications?.slice(0, 6).map((app, index) => (
                  <div key={`app-${app.id ?? index}`} className="rounded-lg border border-slate-200 bg-white p-3">
                    <p className="text-sm font-medium text-slate-800">
                      {app.company ?? "未知企业"} · {app.title ?? "未知岗位"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">状态：{app.status ?? "unknown"}</p>
                    {app.id ? (
                      <Link href={`/applications/${app.id}`} className="mt-1 inline-block text-xs text-sky-700 hover:underline">
                        查看申请详情
                      </Link>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {run ? (
          <div className="border-t border-slate-200 p-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-700">
                  任务状态：{run.status}
                  {run.attempt_count > 1 ? `（第 ${run.attempt_count} 次尝试）` : ""}
                </span>
                {busy ? (
                  <button
                    type="button"
                    onClick={() => void cancel()}
                    className="rounded-md border border-slate-300 px-2 py-1 text-[11px] text-slate-700"
                  >
                    停止任务
                  </button>
                ) : null}
              </div>
              {steps.length ? (
                <ul className="mt-1.5 space-y-0.5">
                  {steps.slice(-6).map((step) => (
                    <li key={step.sequence} className="text-[11px] text-slate-500">
                      #{step.sequence} {step.event_type}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="border-t border-slate-200 p-3">
          <div className="mx-auto flex w-full max-w-2xl items-center gap-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void send();
              }}
              placeholder="输入你的求职需求..."
              disabled={busy}
              className="flex-1 rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm shadow-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:bg-slate-50"
            />
            <button
              type="button"
              onClick={() => void send()}
              disabled={busy || !input.trim()}
              className="rounded-xl bg-slate-900 p-2.5 text-white shadow-sm disabled:opacity-40"
            >
              <Send className="size-4" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => void resume()}
              className="hidden"
            >
              恢复
            </button>
          </div>
          <p className="mt-1 text-[11px] text-slate-400">
            Agent 会调用真实岗位搜索、画像、匹配和进度工具；未配置 LLM 时无法运行。
          </p>
        </div>
      </section>
    </div>
  );
}