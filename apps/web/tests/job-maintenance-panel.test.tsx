import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobMaintenancePanel } from "@/components/job-maintenance-panel";
import type { MaintenanceScope } from "@/lib/api";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }),
}));

const api = vi.hoisted(() => ({
  startJobMaintenance: vi.fn(),
  startJobPrune: vi.fn(),
  getJobMaintenance: vi.fn(),
  cancelJobMaintenance: vi.fn(),
  previewJobPrune: vi.fn(),
  getOfficialSources: vi.fn(),
  getLatestJobMaintenance: vi.fn(),
}));

vi.mock("@/lib/client-api", async (original) => ({ ...(await original<object>()), ...api }));

const scope: MaintenanceScope = {
  q: "大模型",
  companies: [],
  cities: ["北京"],
  job_types: ["internship"],
  source_types: [],
  recruitment_programs: [],
};

const sourceCatalog = [
  { key: "bytedance", label: "字节跳动", supported: true, mode: "rendered", note: "" },
  { key: "alibaba", label: "阿里巴巴", supported: false, mode: "none", note: "需站内签名" },
];

beforeEach(() => {
  vi.clearAllMocks();
  api.getOfficialSources.mockResolvedValue({ ok: true, data: sourceCatalog });
  api.getLatestJobMaintenance.mockResolvedValue({ ok: true, data: null });
  api.previewJobPrune.mockResolvedValue({
    ok: true,
    data: {
      count: 2,
      truncated: false,
      items: [
        {
          job_id: "job-1",
          company: "百度",
          title: "大模型算法实习生",
          city: "北京",
          outcome: "closed",
          closed_checked_at: "2026-11-13T08:00:00Z",
          closed_evidence: "页面明确提示「职位已下架」",
        },
      ],
    },
  });
  api.startJobMaintenance.mockResolvedValue({
    ok: true,
    data: { run_id: "run-1", status: "queued", reused: false },
  });
  api.startJobPrune.mockResolvedValue({
    ok: true,
    data: { run_id: "run-2", status: "queued", reused: false },
  });
  api.getJobMaintenance.mockResolvedValue({
    ok: true,
    data: {
      id: "run-1",
      kind: "refresh",
      status: "running",
      progress: { total: 10, processed: 3, counters: { unchanged: 2, unconfirmed: 1 }, current: "字节跳动 · 岗位" },
      result: {},
      error_message: null,
      created_at: "2026-11-13T08:00:00Z",
      started_at: "2026-11-13T08:00:01Z",
      finished_at: null,
    },
  });
});

afterEach(() => {
  cleanup();
});

describe("岗位库维护面板", () => {
  it("普通用户只看到「更新岗位」，看不到全局清理", () => {
    render(
      <JobMaintenancePanel scope={scope} total={12} isAdmin={false} archivedView={false} />,
    );

    expect(screen.getByRole("button", { name: "更新岗位" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "清理已下线" })).toBeNull();
  });

  it("更新弹窗展示当前范围、单次上限与不支持的来源", async () => {
    render(
      <JobMaintenancePanel scope={scope} total={37} isAdmin={false} archivedView={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "更新岗位" }));

    expect(await screen.findByText(/当前筛选共/)).toBeVisible();
    expect(screen.getByText("37")).toBeVisible();
    expect(screen.getByText("100")).toBeVisible();
    expect(screen.getByLabelText("跳过最近已复核")).toHaveValue("6");
    await waitFor(() => expect(screen.getByText(/阿里巴巴/)).toBeVisible());
    expect(screen.getByLabelText(/复核已有岗位/)).toBeChecked();
    expect(screen.getByLabelText(/发现新增岗位/)).not.toBeChecked();
  });

  it("管理员清理前先看到数量与证据，确认后提交异步任务", async () => {
    render(
      <JobMaintenancePanel scope={scope} total={12} isAdmin archivedView={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "清理已下线" }));

    await waitFor(() => expect(api.previewJobPrune).toHaveBeenCalledWith(scope));
    expect(await screen.findByText(/有明确下线证据的岗位共/)).toBeVisible();
    expect(screen.getByText("2")).toBeVisible();
    expect(screen.getByText(/职位已下架/)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "确认清理" }));

    await waitFor(() => expect(api.startJobPrune).toHaveBeenCalledWith(scope));
  });

  it("提交后展示进度并可取消", async () => {
    render(
      <JobMaintenancePanel scope={scope} total={12} isAdmin={false} archivedView={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "更新岗位" }));
    fireEvent.click(screen.getByRole("button", { name: "开始" }));

    await waitFor(() => expect(api.startJobMaintenance).toHaveBeenCalled());
    expect(api.startJobMaintenance).toHaveBeenCalledWith(
      expect.objectContaining({ max_jobs: 100, cooldown_hours: 6, recheck: true }),
    );
    expect(await screen.findByText(/内容未变/)).toBeVisible();
    expect(screen.getByText(/3 \/ 10/)).toBeVisible();
    expect(screen.getByRole("button", { name: "取消任务" })).toBeInTheDocument();
  });

  it("提交后关闭弹窗，进度面板直接可见", async () => {
    render(
      <JobMaintenancePanel scope={scope} total={12} isAdmin={false} archivedView={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "更新岗位" }));
    expect(screen.getByRole("button", { name: "开始" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "开始" }));

    // The dialog is only a launcher; leaving it open hid the progress it started.
    await waitFor(() => expect(screen.queryByRole("button", { name: "开始" })).toBeNull());
    expect(await screen.findByText(/内容未变/)).toBeVisible();
  });

  it("进入页面时恢复最近一次运行结果", async () => {
    api.getLatestJobMaintenance.mockResolvedValue({
      ok: true,
      data: {
        id: "run-old",
        kind: "discover",
        status: "success",
        progress: { total: 50, processed: 50, counters: { unchanged: 50 } },
        result: { counters: { unchanged: 50 } },
        error_message: null,
        created_at: "2026-11-16T02:00:00Z",
        started_at: "2026-11-16T02:00:01Z",
        finished_at: "2026-11-16T02:00:04Z",
      },
    });

    render(
      <JobMaintenancePanel scope={scope} total={12} isAdmin={false} archivedView={false} />,
    );

    expect(await screen.findByText(/更新岗位 · success/)).toBeVisible();
    expect(screen.getByText(/50 \/ 50/)).toBeVisible();
  });
});
