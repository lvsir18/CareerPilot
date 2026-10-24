"use client";

import { Bot, Menu, Pencil, Plus, Send, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { AgentMessageBubble } from "@/components/agent-message";
import {
  cancelAgentRun,
  createAgentRun,
  createAgentThread,
  deleteAgentThread,
  getAgentRun,
  listAgentMessages,
  listAgentThreadRuns,
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
import {
  formatAgentEventType,
  formatAgentRunStatus,
  formatApplicationStatus,
  formatEligibility,
  formatJobType,
  formatVerificationStatus,
} from "@/lib/job-display";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "帮我找北京的大模型实习",
  "哪些岗位更适合我的简历？",
  "看看我最近的申请进度",
];

/** Statuses that still receive live events from the stream. */
const LIVE_STATUSES = ["queued", "running"];
const TERMINAL_STATUSES = ["completed", "partial", "failed", "cancelled", "timed_out"];
/** Any of these means the worker is done, even without a run.final frame. */
const TERMINAL_EVENTS = [
  "run.completed",
  "run.partial",
  "run.failed",
  "run.cancelled",
  "run.timed_out",
];

/** Run status implied by lifecycle events that carry no status field. */
const STATUS_BY_EVENT: Record<string, string> = {
  "run.queued": "queued",
  "run.started": "running",
  "run.resumed": "running",
  "approval.required": "waiting_for_user",
  "run.cancelled": "cancelled",
};

const STREAM_EVENTS = [
  "run.queued",
  "run.started",
  "run.resumed",
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

/** Append an assistant answer only when the message list does not have it yet. */
function withAnswer(list: AgentMessage[], answer: string | null | undefined): AgentMessage[] {
  if (!answer) {
    return list;
  }
  const last = list[list.length - 1];
  if (last && last.role === "assistant" && last.content === answer) {
    return list;
  }
  return [...list, { role: "assistant", content: answer }];
}

function AgentPageInner() {
  const searchParams = useSearchParams();
  // The hand-off query is a route param, not a one-off DOM read: during a
  // client-side navigation the previous page's URL is still in window.location
  // when this component first renders, which is how the filters were lost.
  const handoffQuery = searchParams.get("q") ?? "";
  const requestedThread = searchParams.get("thread") ?? "";
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [current, setCurrent] = useState<AgentThread | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [input, setInput] = useState(handoffQuery);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [structured, setStructured] = useState<AgentRunResult["structured"]>(null);
  // Async execution state: the run is created immediately, then followed via SSE.
  const [run, setRun] = useState<AgentRun | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [steps, setSteps] = useState<AgentRunEventItem[]>([]);
  // HITL: the run paused on waiting_for_user and needs an explicit continue.
  const [waitingApproval, setWaitingApproval] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const loadToken = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<EventSource | null>(null);
  const creatingThread = useRef<Promise<AgentThread | null> | null>(null);
  const appliedHandoff = useRef(handoffQuery);
  const openedThread = useRef<string | null>(null);

  const detachStream = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
  }, []);

  const refreshThreads = useCallback(async () => {
    const result = await listAgentThreads();
    if (!result.ok) {
      return;
    }
    setThreads(result.data);
    setCurrent((prev) => (prev ? (result.data.find((t) => t.id === prev.id) ?? prev) : prev));
  }, []);

  const finishRun = useCallback(
    (status: string, result: AgentRunResult | null) => {
      detachStream();
      setBusy(false);
      setLoadingMessages(false);
      setRunStatus(status);
      setRun((prev) => (prev ? { ...prev, status } : prev));
      setWaitingApproval(status === "waiting_for_user");
      if (result) {
        setMessages((prev) => withAnswer(prev, result.final_answer));
        setStructured(result.structured ?? null);
      }
      void refreshThreads();
    },
    [detachStream, refreshThreads],
  );

  const followRun = useCallback(
    (runId: string) => {
      detachStream();
      // Bind this subscription to the thread generation it was created for: a
      // stream/poll left over from a previous thread must never write into the
      // conversation the user is looking at now.
      const generation = loadToken.current;
      const stale = () => loadToken.current !== generation;
      const source = new EventSource(`/api/v1/agent/runs/${runId}/stream`);
      streamRef.current = source;
      let finished = false;

      const handle = (eventType: string) => (event: Event) => {
        if (stale()) {
          source.close();
          return;
        }
        let parsed: {
          sequence?: number;
          event_type?: string;
          payload?: Record<string, unknown>;
          status?: string;
          result?: AgentRunResult | null;
        };
        try {
          parsed = JSON.parse((event as MessageEvent<string>).data);
        } catch {
          return;
        }
        const sequence = parsed.sequence ?? 0;
        setSteps((prev) =>
          prev.some((item) => item.sequence === sequence)
            ? prev
            : [
                ...prev,
                {
                  sequence,
                  event_type: parsed.event_type ?? eventType,
                  safe_payload: parsed.payload ?? {},
                  created_at: new Date().toISOString(),
                },
              ],
        );
        const status =
          parsed.status ??
          (parsed.payload?.status as string | undefined) ??
          STATUS_BY_EVENT[eventType];
        if (status) {
          setRunStatus(status);
        }
        // Only the final event ends the run: run.queued / run.started are
        // perfectly normal intermediate states and must not stop the stream.
        if (eventType === "run.final") {
          if (finished) return;
          finished = true;
          finishRun(String(status ?? "completed"), parsed.result ?? null);
          return;
        }
        // Defensive: if the stream ends without run.final, a terminal worker
        // event still stops follow-up and pulls the authoritative record.
        if (TERMINAL_EVENTS.includes(eventType)) {
          if (finished) return;
          finished = true;
          detachStream();
          void pollRun(runId, finishRun, stale);
        }
      };

      for (const type of STREAM_EVENTS) {
        source.addEventListener(type, handle(type));
      }

      source.onerror = () => {
        if (stale()) {
          source.close();
          return;
        }
        if (finished) return;
        finished = true;
        detachStream();
        void pollRun(runId, finishRun, stale);
      };
    },
    [detachStream, finishRun],
  );

  /** Re-attach to the newest run of a thread after refresh/thread switch. */
  const restoreRun = useCallback(
    async (threadId: string, token: number) => {
      const runs = await listAgentThreadRuns(threadId, 1);
      if (loadToken.current !== token || !runs.ok) {
        return;
      }
      const latest = runs.data[0];
      if (!latest) {
        return;
      }
      setRun(latest);
      setRunStatus(latest.status);
      if (LIVE_STATUSES.includes(latest.status)) {
        setBusy(true);
        followRun(latest.id);
        return;
      }
      if (latest.status === "waiting_for_user") {
        setWaitingApproval(true);
      }
      if (latest.result) {
        setMessages((prev) => withAnswer(prev, latest.result?.final_answer));
        setStructured(latest.result.structured ?? null);
      }
    },
    [followRun],
  );

  const openThread = useCallback(
    async (thread: AgentThread) => {
      openedThread.current = thread.id;
      const token = loadToken.current + 1;
      loadToken.current = token;
      detachStream();
      setCurrent(thread);
      setBusy(false);
      setError(null);
      setStructured(null);
      setRun(null);
      setRunStatus(null);
      setWaitingApproval(false);
      setSteps([]);
      setMessages([]);
      setSidebarOpen(false);
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
      await restoreRun(thread.id, token);
    },
    [detachStream, restoreRun],
  );

  // URL changes within this page must not detach its current subscription.
  // Actual thread switches do so in openThread/newThread; unmount does it here.
  useEffect(() => {
    return () => {
      loadToken.current += 1;
      detachStream();
    };
  }, [detachStream]);

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
      // A hand-off starts a fresh conversation: reusing the most recent thread
      // both hides the new question among old answers and drops ?q= from the URL.
      const target = requestedThread
        ? result.data.find((item) => item.id === requestedThread)
        : handoffQuery
          ? undefined
          : result.data[0];
      // ``syncThreadUrl`` below rewrites the URL, which re-runs this effect; the
      // ref keeps that from opening the same thread twice.
      if (target && target.id !== openedThread.current) {
        openedThread.current = target.id;
        await openThread(target);
      }
    })();
    return () => {
      active = false;
    };
  }, [detachStream, openThread, requestedThread, handoffQuery]);

  // Keep the composer in sync when the route param changes without a remount.
  useEffect(() => {
    if (!handoffQuery || handoffQuery === appliedHandoff.current) {
      return;
    }
    appliedHandoff.current = handoffQuery;
    setInput(handoffQuery);
  }, [handoffQuery]);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, loadingMessages, busy]);

  async function newThread() {
    const pending = (async () => {
      const result = await createAgentThread();
      if (!result.ok) {
        setError(result.error.message);
        return null;
      }
      setThreads((prev) => [result.data, ...prev]);
      openedThread.current = result.data.id;
      loadToken.current += 1;
      detachStream();
      setCurrent(result.data);
      setMessages([]);
      setLoadingMessages(false);
      setStructured(null);
      setRun(null);
      setRunStatus(null);
      // Switching threads detaches the live stream: release the composer instead
      // of leaving it disabled forever.
      setBusy(false);
      setWaitingApproval(false);
      setSteps([]);
      setError(null);
      setSidebarOpen(false);
      syncThreadUrl(result.data.id);
      return result.data;
    })();
    creatingThread.current = pending;
    try {
      await pending;
    } finally {
      creatingThread.current = null;
    }
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
      openedThread.current = null;
      loadToken.current += 1;
      detachStream();
      setCurrent(null);
      setMessages([]);
      setLoadingMessages(false);
      setBusy(false);
      setSteps([]);
      setStructured(null);
      setRun(null);
      setRunStatus(null);
      setWaitingApproval(false);
      syncThreadUrl(null);
    }
    void refreshThreads();
  }

  async function send() {
    const text = input.trim();
    if (!text || busy || loadingMessages) return;

    // A thread created milliseconds ago may still be in flight; binding the run
    // to the older thread is what produced the mis-associated run in testing.
    let thread = current;
    if (creatingThread.current) {
      const created = await creatingThread.current;
      if (created) {
        thread = created;
      }
    }
    if (!thread) {
      const created = await createAgentThread();
      if (!created.ok) {
        setError(created.error.message);
        return;
      }
      thread = created.data;
      openedThread.current = created.data.id;
      setThreads((prev) => [created.data, ...prev]);
      setCurrent(created.data);
      syncThreadUrl(created.data.id);
    }

    const threadId = thread.id;
    const token = loadToken.current + 1;
    loadToken.current = token;
    setBusy(true);
    setError(null);
    setSteps([]);
    setRunStatus("queued");
    setWaitingApproval(false);
    const userMessage: AgentMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    // Mirror the backend auto-title immediately so the sidebar stops showing
    // "新对话" while the first run is still queued.
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
      setRunStatus(null);
      setError(result.error.message);
      return;
    }
    // The user may have switched threads while the run was being created; the
    // run belongs to the old thread and must not hijack the new one.
    if (loadToken.current !== token) {
      void refreshThreads();
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
    const token = loadToken.current + 1;
    loadToken.current = token;
    setBusy(true);
    setError(null);
    setRunStatus("queued");
    const result = await resumeAgent(current.id, true);
    if (loadToken.current !== token) {
      return;
    }
    if (!result.ok) {
      // The server refuses to resume an unconfirmed profile; stay on the
      // approval card instead of pretending the run continued.
      setBusy(false);
      setRunStatus("waiting_for_user");
      setWaitingApproval(true);
      setError(result.error.message);
      return;
    }
    setWaitingApproval(false);
    setRun(result.data);
    followRun(result.data.id);
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

  const hasCards = Boolean(
    structured &&
      (structured.jobs?.length ||
        structured.matches?.length ||
        structured.extra_matches?.length ||
        structured.applications?.length),
  );

  // Eligible matches first and the rest explicitly labelled: the same styling
  // for a 运营 job the user cannot apply to read as "recommended".
  const matchCards = structured?.matches ?? [];
  const orderedMatches = [
    ...matchCards.filter((item) => item.match?.eligibility_status !== "ineligible"),
    ...matchCards.filter((item) => item.match?.eligibility_status === "ineligible"),
  ];

  return (
    <div className="relative flex h-[calc(100vh-6rem)] min-w-0 gap-4 overflow-hidden">
      {sidebarOpen ? (
        <button
          type="button"
          aria-label="关闭会话列表"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-10 bg-slate-900/20 md:hidden"
        />
      ) : null}
      <aside
        className={cn(
          "z-20 w-72 shrink-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white p-3 shadow-sm md:flex md:w-60",
          sidebarOpen ? "absolute inset-y-0 left-0 flex" : "hidden",
        )}
      >
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void newThread()}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white"
          >
            <Plus className="size-4" aria-hidden />
            新建对话
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            aria-label="关闭会话列表"
            className="rounded-md p-2 text-slate-400 hover:text-slate-700 md:hidden"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
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

      <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex min-w-0 items-center gap-2 border-b border-slate-200 px-4 py-3">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="打开会话列表"
            className="rounded-md p-1 text-slate-500 hover:text-slate-800 md:hidden"
          >
            <Menu className="size-4" aria-hidden />
          </button>
          <Bot className="size-4 shrink-0 text-slate-400" aria-hidden />
          {current ? (
            editingId === current.id ? (
              renderTitleEditor(current, "w-40 md:w-64")
            ) : (
              <>
                <span className="min-w-0 max-w-[12rem] truncate text-sm font-medium text-slate-700 md:max-w-[24rem]">
                  {current.title}
                </span>
                <button
                  type="button"
                  onClick={() => startRename(current)}
                  aria-label="重命名当前会话"
                  title="重命名"
                  className="shrink-0 rounded p-1 text-slate-400 hover:text-slate-700"
                >
                  <Pencil className="size-3" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => void removeThread(current)}
                  aria-label="删除当前会话"
                  title="删除会话"
                  className="shrink-0 rounded p-1 text-slate-400 hover:text-rose-600"
                >
                  <Trash2 className="size-3" aria-hidden />
                </button>
              </>
            )
          ) : (
            <span className="min-w-0 truncate text-sm font-medium text-slate-700">智能求职助手</span>
          )}
          <Link
            href="/discover"
            className="ml-auto hidden shrink-0 text-xs text-sky-700 hover:underline sm:block"
          >
            在招聘中心查看
          </Link>
        </div>

        <div ref={scrollRef} className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-4">
          <div className="mx-auto w-full max-w-2xl min-w-0 space-y-3">
            {loadingMessages ? (
              <p className="text-sm text-slate-500">正在加载会话…</p>
            ) : messages.length === 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-500">
                  {current
                    ? "问我「帮我找字节和小红书的大模型实习」或「哪些岗位更适合我的简历」。"
                    : "从会话列表选择一个历史对话，或直接输入需求开始新对话。"}
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
            {error ? <p className="break-words text-sm text-rose-700">{error}</p> : null}

            {hasCards && structured ? (
              <div className="space-y-2">
                {structured.jobs?.slice(0, 6).map((job, index) => (
                  <div
                    key={`job-${job.id ?? index}`}
                    className="min-w-0 rounded-lg border border-slate-200 bg-white p-3"
                  >
                    <p className="break-words text-sm font-medium text-slate-800">
                      {job.company ?? "未知企业"} · {job.title ?? "未知岗位"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {job.city ?? "城市未知"} · {formatJobType(job.job_type)}
                      {job.verification_status
                        ? ` · ${formatVerificationStatus(job.verification_status)}`
                        : ""}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs">
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
                      <Link
                        href={`/discover?q=${encodeURIComponent(job.title ?? "")}`}
                        className="text-slate-600 hover:underline"
                      >
                        在招聘中心查看
                      </Link>
                    </div>
                  </div>
                ))}

                {orderedMatches.slice(0, 6).map((item, index) => (
                  <div
                    key={`match-${item.job?.id ?? index}`}
                    className={
                      item.match?.eligibility_status === "ineligible"
                        ? "min-w-0 rounded-lg border border-rose-200 bg-rose-50/40 p-3"
                        : "min-w-0 rounded-lg border border-slate-200 bg-white p-3"
                    }
                  >
                    <p className="break-words text-sm font-medium text-slate-800">
                      {item.job?.company ?? "未知企业"} · {item.job?.title ?? "未知岗位"}
                      {item.match?.eligibility_status === "ineligible" ? (
                        <span className="ml-2 rounded-full bg-rose-100 px-1.5 py-0.5 align-middle text-[10px] font-normal text-rose-700">
                          资格不符 · 仅供参考
                        </span>
                      ) : null}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      匹配{" "}
                      {item.match?.match_score != null
                        ? `${item.match.match_score}/100`
                        : "信息不足"}{" "}
                      · {formatEligibility(item.match?.eligibility_status)}
                    </p>
                    {item.match?.matched_skills?.length ? (
                      <p className="mt-1 break-words text-xs text-emerald-700">
                        命中：{item.match.matched_skills.join("、")}
                      </p>
                    ) : null}
                    {item.match?.unverified_skills?.length ? (
                      <p className="mt-0.5 break-words text-xs text-slate-500">
                        未体现：{item.match.unverified_skills.join("、")}
                      </p>
                    ) : null}
                    <div className="mt-1 flex flex-wrap gap-3 text-xs">
                      {item.job?.id ? (
                        <Link href={`/jobs/${item.job.id}`} className="text-sky-700 hover:underline">
                          详情
                        </Link>
                      ) : null}
                      {item.job?.source_url ? (
                        <a
                          href={item.job.source_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-slate-600 hover:underline"
                        >
                          官网
                        </a>
                      ) : null}
                    </div>
                  </div>
                ))}

                {structured.extra_matches?.length ? (
                  <details className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <summary className="cursor-pointer text-xs text-slate-600">
                      另有 {structured.extra_matches.length} 个候选未列入本轮条件
                    </summary>
                    <ul className="mt-2 space-y-1">
                      {structured.extra_matches.slice(0, 10).map((item, index) => (
                        <li
                          key={`extra-${item.job?.id ?? index}`}
                          className="break-words text-xs text-slate-500"
                        >
                          {item.job?.company ?? "未知企业"} · {item.job?.title ?? "未知岗位"}
                          <span className="ml-1 text-slate-400">
                            （{item.selection_reason ?? "未列入本轮条件"}）
                          </span>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}

                {structured.applications?.slice(0, 6).map((app, index) => (
                  <div
                    key={`app-${app.id ?? index}`}
                    className="min-w-0 rounded-lg border border-slate-200 bg-white p-3"
                  >
                    <p className="break-words text-sm font-medium text-slate-800">
                      {app.company ?? "未知企业"} · {app.title ?? "未知岗位"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      状态：{app.status ? formatApplicationStatus(app.status) : "未知"}
                    </p>
                    {app.id ? (
                      <Link
                        href={`/applications/${app.id}`}
                        className="mt-1 inline-block text-xs text-sky-700 hover:underline"
                      >
                        查看申请详情
                      </Link>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {run && runStatus ? (
          <div className="border-t border-slate-200 p-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-slate-700">
                  任务状态：{formatAgentRunStatus(runStatus)}
                  {run.attempt_count > 1 ? `（第 ${run.attempt_count} 次尝试）` : ""}
                  {runStatus === "partial" && run.error_summary
                    ? ` · ${run.error_summary}`
                    : ""}
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
                      #{step.sequence} {formatAgentEventType(step.event_type)}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        ) : null}

        {waitingApproval ? (
          <div className="border-t border-amber-200 bg-amber-50 p-3">
            <p className="text-xs text-amber-900">
              这次任务需要先确认画像才能继续：确认后点「已确认，继续」即可完成本次匹配。
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Link
                href="/profile"
                className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
              >
                去确认画像
              </Link>
              <button
                type="button"
                onClick={() => void resume()}
                disabled={busy}
                className="rounded-md border border-amber-400 bg-white px-3 py-1.5 text-xs font-medium text-amber-900 disabled:opacity-50"
              >
                已确认，继续
              </button>
            </div>
          </div>
        ) : null}

        <div className="border-t border-slate-200 p-3">
          <div className="mx-auto flex w-full max-w-2xl min-w-0 items-center gap-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void send();
              }}
              placeholder="输入你的求职需求..."
              disabled={busy}
              className="min-w-0 flex-1 rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm shadow-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:bg-slate-50"
            />
            <button
              type="button"
              onClick={() => void send()}
              disabled={busy || loadingMessages || !input.trim()}
              aria-label="发送"
              className="shrink-0 rounded-xl bg-slate-900 p-2.5 text-white shadow-sm disabled:opacity-40"
            >
              <Send className="size-4" aria-hidden />
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

/** Fallback polling used when the SSE connection cannot be established. */
async function pollRun(
  runId: string,
  finish: (status: string, result: AgentRunResult | null) => void,
  isStale: () => boolean = () => false,
) {
  for (let i = 0; i < 120; i += 1) {
    // Stop polling for a thread the user already left: the old run's answer must
    // not be written into the newly opened conversation.
    if (isStale()) {
      return;
    }
    const result = await getAgentRun(runId);
    if (isStale()) {
      return;
    }
    if (!result.ok) {
      finish("failed", null);
      return;
    }
    if (result.data.status === "waiting_for_user") {
      finish("waiting_for_user", result.data.result);
      return;
    }
    if (TERMINAL_STATUSES.includes(result.data.status)) {
      finish(result.data.status, result.data.result);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  finish("timed_out", null);
}

// useSearchParams needs a Suspense boundary when the route is prerendered.
export default function AgentPage() {
  return (
    <Suspense
      fallback={<p className="p-6 text-sm text-slate-500">正在打开求职助手…</p>}
    >
      <AgentPageInner />
    </Suspense>
  );
}
