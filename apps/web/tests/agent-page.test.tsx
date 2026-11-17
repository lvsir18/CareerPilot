import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AgentPage from "@/app/(app)/agent/page";
import type { AgentRun, AgentRunResult, AgentThread } from "@/lib/api";

const api = vi.hoisted(() => ({
  listAgentThreads: vi.fn(), listAgentMessages: vi.fn(), listAgentThreadRuns: vi.fn(),
  createAgentThread: vi.fn(), createAgentRun: vi.fn(),
}));
vi.mock("@/lib/client-api", async (original) => ({ ...await original<object>(), ...api }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(window.location.search) }));
const thread = (id: string): AgentThread => ({ id, title: id, status: "active", created_at: "", updated_at: "" });
const result: AgentRunResult = {
  thread_id: "new-thread", status: "completed", intent: "profile_query", constraints: {},
  plan: [], agent_results: {}, final_answer: "新会话的技术技能回答", errors: [],
  structured: { jobs: [], matches: [], applications: [], progress_events: [] },
};
const run: AgentRun = {
  id: "new-run", thread_id: "new-thread", request_id: "request", status: "running", result: null,
  error_code: null, error_summary: null, created_at: "", started_at: null, finished_at: null,
  cancel_requested_at: null, attempt_count: 1,
};
class Stream extends EventTarget {
  static instances: Stream[] = [];
  onerror: (() => void) | null = null;
  closed = false;
  constructor(readonly url: string) { super(); Stream.instances.push(this); }
  close() { this.closed = true; }
  emit(type: string, payload: Record<string, unknown>) {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(payload) }));
  }
  finish() {
    this.dispatchEvent(new MessageEvent("run.final", { data: JSON.stringify({ status: "completed", sequence: 1, result }) }));
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/agent");
  Stream.instances = [];
  vi.stubGlobal("EventSource", Stream);
  api.listAgentThreads.mockResolvedValue({ ok: true, data: [] });
  api.listAgentMessages.mockResolvedValue({ ok: true, data: [] });
  api.listAgentThreadRuns.mockResolvedValue({ ok: true, data: [] });
  api.createAgentThread.mockImplementation(async () => {
    api.listAgentThreads.mockResolvedValue({ ok: true, data: [thread("new-thread")] });
    return { ok: true, data: thread("new-thread") };
  });
  api.createAgentRun.mockResolvedValue({ ok: true, data: run });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
async function sendImmediately() {
  fireEvent.change(screen.getByPlaceholderText("输入你的求职需求..."), { target: { value: "列出技能" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(Stream.instances).toHaveLength(1));
  const stream = Stream.instances[0]!;
  expect(stream.closed).toBe(false);
  act(() => stream.finish());
  expect(await screen.findByText(result.final_answer!)).toBeVisible();
  expect(screen.queryByText("正在加载会话…")).not.toBeInTheDocument();
}
function follows(anchor: Node, target: Node): boolean {
  return Boolean(anchor.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING);
}

function historyRun(message: string, answer: string, jobTitle: string, city: string): AgentRun {
  return {
    ...run,
    id: `run-${city}`,
    thread_id: "history-thread",
    status: "completed",
    input_message: message,
    result: {
      ...result,
      final_answer: answer,
      structured: {
        jobs: [
          {
            id: `job-${city}`,
            company: "字节跳动",
            title: jobTitle,
            city,
            job_type: "internship",
            verification_status: "verified",
            source_url: "https://jobs.example.test/1",
          },
        ],
        matches: [],
        applications: [],
        progress_events: [],
      },
    },
  };
}

describe("Agent conversation lifecycle", () => {
  it("新建后立即发送不会因 URL 同步而重新加载会话或丢掉订阅", async () => {
    render(<AgentPage />);
    fireEvent.click(screen.getByRole("button", { name: "新建对话" }));
    await waitFor(() => expect(window.location.search).toContain("thread=new-thread"));
    await sendImmediately();
    expect(api.listAgentMessages).not.toHaveBeenCalled();
  });
  it("旧消息请求延迟返回时，不能遮住新会话已完成的回答", async () => {
    const old = deferred<{ ok: true; data: { role: string; content: string }[] }>();
    api.listAgentThreads.mockResolvedValue({ ok: true, data: [thread("old-thread")] });
    api.listAgentMessages.mockReturnValue(old.promise);
    render(<AgentPage />);
    expect(await screen.findByText("正在加载会话…")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "新建对话" }));
    await waitFor(() => expect(window.location.search).toContain("thread=new-thread"));
    await sendImmediately();
    await act(async () => { old.resolve({ ok: true, data: [{ role: "assistant", content: "旧会话的迟到回答" }] }); });
    expect(screen.getByText(result.final_answer!)).toBeVisible();
    expect(screen.queryByText("旧会话的迟到回答")).not.toBeInTheDocument();
  });
  it("只有未入选候选时仍显示折叠入口", async () => {
    api.listAgentThreads.mockResolvedValue({ ok: true, data: [thread("new-thread")] });
    api.listAgentThreadRuns.mockResolvedValue({ ok: true, data: [{ ...run, status: "completed", result: {
      ...result, structured: { ...result.structured!, extra_matches: [{
        job: { id: "excluded", title: "运营实习生", company: "百度" },
        match: { match_score: 25 }, selection_reason: "不在本轮限定的岗位方向",
      }] },
    } }] });
    render(<AgentPage />);
    expect(await screen.findByText("另有 1 个候选未列入本轮条件")).toBeVisible();
    fireEvent.click(screen.getByText("另有 1 个候选未列入本轮条件"));
    expect(screen.getByText(/运营实习生/)).toBeVisible();
  });
  it("旧订阅的迟到事件不能关闭新会话的 SSE", async () => {
    api.listAgentThreads.mockResolvedValue({ ok: true, data: [thread("old-thread")] });
    api.listAgentThreadRuns.mockResolvedValue({ ok: true, data: [{ ...run, id: "old-run", thread_id: "old-thread" }] });
    render(<AgentPage />);
    await waitFor(() => expect(Stream.instances).toHaveLength(1));
    const old = Stream.instances[0]!;
    fireEvent.click(screen.getByRole("button", { name: "新建对话" }));
    await waitFor(() => expect(window.location.search).toContain("thread=new-thread"));
    fireEvent.change(screen.getByPlaceholderText("输入你的求职需求..."), { target: { value: "新问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(Stream.instances).toHaveLength(2));
    act(() => old.finish());
    expect(Stream.instances[1]!.closed).toBe(false);
    expect(screen.queryByText(result.final_answer!)).not.toBeInTheDocument();
    act(() => Stream.instances[1]!.finish());
    expect(await screen.findByText(result.final_answer!)).toBeVisible();
  });
  it("重开历史会话时，每轮岗位卡片跟着自己那轮回答", async () => {
    window.history.replaceState(null, "", "/agent?thread=history-thread");
    api.listAgentThreads.mockResolvedValue({ ok: true, data: [thread("history-thread")] });
    api.listAgentThreadRuns.mockResolvedValue({
      ok: true,
      data: [
        historyRun("帮我找北京的大模型实习", "北京回答", "北京岗位A", "北京"),
        historyRun("再找一下杭州的呢", "杭州回答", "杭州岗位B", "杭州"),
      ],
    });

    render(<AgentPage />);

    const firstAnswer = await screen.findByText("北京回答");
    const firstCard = screen.getByText(/北京岗位A/);
    const secondQuestion = screen.getByText("再找一下杭州的呢");
    const secondCard = screen.getByText(/杭州岗位B/);

    expect(follows(firstAnswer, firstCard)).toBe(true);
    // 北京卡片必须停在「北京回答」与「杭州问题」之间。
    expect(follows(firstCard, secondQuestion)).toBe(true);
    expect(follows(secondQuestion, secondCard)).toBe(true);
  });
  it("发送新问题时，上一轮的卡片不会被挤到新问题下面，也不会被清空", async () => {
    window.history.replaceState(null, "", "/agent?thread=history-thread");
    api.listAgentThreads.mockResolvedValue({ ok: true, data: [thread("history-thread")] });
    api.listAgentThreadRuns.mockResolvedValue({
      ok: true,
      data: [historyRun("帮我找北京的大模型实习", "北京回答", "北京岗位A", "北京")],
    });

    render(<AgentPage />);

    const firstAnswer = await screen.findByText("北京回答");
    const firstCard = screen.getByText(/北京岗位A/);
    fireEvent.change(screen.getByPlaceholderText("输入你的求职需求..."), {
      target: { value: "再找一下杭州的呢" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(Stream.instances).toHaveLength(1));

    const newQuestion = await screen.findByText("再找一下杭州的呢");
    expect(follows(firstAnswer, firstCard)).toBe(true);
    expect(follows(firstCard, newQuestion)).toBe(true);
  });
  it("新建对话按钮在会话列表顶部，不占用输入区", async () => {
    render(<AgentPage />);

    const button = screen.getByRole("button", { name: "新建对话" });
    const input = screen.getByPlaceholderText("输入你的求职需求...");

    expect(button.closest("aside")).not.toBeNull();
    expect(button.parentElement).not.toBe(input.parentElement);
  });
  it("工作台按父容器高度铺满，不再用固定视口偏移", async () => {
    const { container } = render(<AgentPage />);

    const root = container.querySelector("div.relative.flex");
    expect(root?.className).toContain("h-full");
    expect(root?.className).not.toContain("100vh");
  });
  it("任务状态面板保留全部步骤，并提供滚动区域", async () => {
    render(<AgentPage />);
    fireEvent.click(screen.getByRole("button", { name: "新建对话" }));
    await waitFor(() => expect(window.location.search).toContain("thread=new-thread"));
    fireEvent.change(screen.getByPlaceholderText("输入你的求职需求..."), {
      target: { value: "帮我找岗位" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(Stream.instances).toHaveLength(1));

    const stream = Stream.instances[0]!;
    act(() => {
      for (let sequence = 1; sequence <= 8; sequence += 1) {
        stream.emit("tool.started", { sequence, event_type: "tool.started" });
      }
    });

    const list = await screen.findByLabelText("任务执行步骤");
    expect(list.className).toContain("overflow-y-auto");
    // 全部步骤都在（以前只渲染最后 6 条）。
    expect(screen.getByText("#1 调用工具")).toBeVisible();
    expect(screen.getByText("#8 调用工具")).toBeVisible();
  });
});
