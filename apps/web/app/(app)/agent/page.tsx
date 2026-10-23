"use client";

import { Bot, Plus, Send } from "lucide-react";
import { useEffect, useState } from "react";
import Link from "next/link";

import {
  cancelAgentRun,
  createAgentRun,
  createAgentThread,
  getAgentRun,
  listAgentMessages,
  listAgentThreads,
  resumeAgent,
} from "@/lib/client-api";
import type {
  AgentMessage,
  AgentRun,
  AgentRunEventItem,
  AgentRunResult,
  AgentThread,
} from "@/lib/api";

export default function AgentPage() {
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [current, setCurrent] = useState<AgentThread | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
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

  async function refreshThreads() {
    const result = await listAgentThreads();
    if (result.ok) setThreads(result.data);
  }

  async function openThread(thread: AgentThread) {
    setCurrent(thread);
    setError(null);
    const result = await listAgentMessages(thread.id);
    setMessages(result.ok ? result.data : []);
  }

  async function newThread() {
    const result = await createAgentThread();
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setCurrent(result.data);
    setMessages([]);
    await refreshThreads();
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
    if (!input.trim() || !current) return;
    setBusy(true);
    setError(null);
    setSteps([]);
    const userMessage: AgentMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    const result = await createAgentRun({
      thread_id: current.id,
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

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch then setState
    void refreshThreads();
  }, []);

  return (
    <div className="flex h-[calc(100vh-6rem)] gap-4">
      <aside className="w-56 shrink-0 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <button
          type="button"
          onClick={() => void newThread()}
          className="flex w-full items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white"
        >
          <Plus className="size-4" aria-hidden />
          新建对话
        </button>
        <div className="mt-3 space-y-1">
          {threads.map((thread) => (
            <button
              key={thread.id}
              type="button"
              onClick={() => void openThread(thread)}
              className={`block w-full truncate rounded-lg px-3 py-2 text-left text-xs ${
                current?.id === thread.id
                  ? "bg-sky-50 text-sky-700"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {thread.title}
            </button>
          ))}
        </div>
      </aside>

      <section className="flex flex-1 flex-col rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
          <Bot className="size-4 text-slate-400" aria-hidden />
          <span className="text-sm font-medium text-slate-700">智能求职助手</span>
          <Link href="/discover" className="ml-auto text-xs text-sky-700 hover:underline">
            在招聘中心查看
          </Link>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <p className="text-sm text-slate-500">
              问我「帮我找字节和小红书的大模型实习」或「哪些岗位更适合我的简历」。
            </p>
          ) : (
            messages.map((message, index) => (
              <div
                key={index}
                className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${
                  message.role === "user"
                    ? "ml-auto bg-sky-50 text-slate-800"
                    : "bg-slate-100 text-slate-700"
                }`}
              >
                {message.content}
              </div>
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
          <div className="flex items-center gap-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void send();
              }}
              placeholder="输入你的求职需求..."
              disabled={busy || !current}
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-500"
            />
            <button
              type="button"
              onClick={() => void send()}
              disabled={busy || !current || !input.trim()}
              className="rounded-lg bg-slate-900 p-2 text-white disabled:opacity-40"
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
