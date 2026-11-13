import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";

const api = vi.hoisted(() => ({
  getActivity: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("@/lib/client-api", () => api);

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("侧边导航的后台任务标记", () => {
  it("岗位库有活跃维护任务时显示加载图标", async () => {
    api.getActivity.mockResolvedValue({
      ok: true,
      data: {
        job_maintenance: {
          run_id: "run-1",
          kind: "refresh",
          status: "running",
          total: 40,
          processed: 3,
        },
        agent: null,
      },
    });

    render(<AppShell userEmail="user@example.com">内容</AppShell>);

    await waitFor(() => expect(screen.getByLabelText("后台任务运行中")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /岗位库/ })).toContainElement(
      screen.getByLabelText("后台任务运行中"),
    );
  });

  it("Agent 有进行中的对话时在 Agent 工作台旁显示图标", async () => {
    api.getActivity.mockResolvedValue({
      ok: true,
      data: {
        job_maintenance: null,
        agent: { run_id: "run-2", thread_id: "thread-1", status: "running" },
      },
    });

    render(<AppShell userEmail="user@example.com">内容</AppShell>);

    await waitFor(() => expect(screen.getByLabelText("后台任务运行中")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Agent 工作台/ })).toContainElement(
      screen.getByLabelText("后台任务运行中"),
    );
  });

  it("没有后台任务时不显示加载图标", async () => {
    api.getActivity.mockResolvedValue({
      ok: true,
      data: { job_maintenance: null, agent: null },
    });

    render(<AppShell userEmail="user@example.com">内容</AppShell>);

    await waitFor(() => expect(api.getActivity).toHaveBeenCalled());
    expect(screen.queryByLabelText("后台任务运行中")).toBeNull();
  });
});
