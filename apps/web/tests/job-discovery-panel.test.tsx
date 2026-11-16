import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobDiscoveryPanel } from "@/components/job-discovery-panel";

const api = vi.hoisted(() => ({
  discoverJobs: vi.fn(),
  getOfficialSources: vi.fn(),
  searchOfficialJobs: vi.fn(),
  verifyJobLead: vi.fn(),
  verifyJobLeads: vi.fn(),
  getPendingLeadCount: vi.fn(),
  startLeadVerification: vi.fn(),
  getJobMaintenance: vi.fn(),
  getActivity: vi.fn(),
}));

vi.mock("@/lib/client-api", async (original) => ({ ...(await original<object>()), ...api }));

beforeEach(() => {
  vi.clearAllMocks();
  api.getOfficialSources.mockResolvedValue({ ok: true, data: [] });
  api.getPendingLeadCount.mockResolvedValue({ ok: true, data: { count: 0 } });
  api.getActivity.mockResolvedValue({
    ok: true,
    data: { job_maintenance: null, agent: null },
  });
  api.discoverJobs.mockResolvedValue({
    ok: true,
    data: {
      query: "",
      companies: [],
      job_family: "",
      sort: "relevance",
      verification: "all",
      published_within_days: null,
      page: 1,
      page_size: 20,
      total_pages: 1,
      jobs: [],
      leads: [],
      total_jobs: 0,
      total_leads: 0,
      search: {
        configured: true,
        licensed_configured: true,
        providers_used: [],
        provider_results: [],
        provider_statuses: [],
        warnings: [],
        discovery_window_days: null,
        searched_at: null,
        tavily_queries: 0,
        tavily_cached_queries: 0,
        credits_estimated: 0,
        diagnostics: [],
      },
    },
  });
});

afterEach(() => {
  cleanup();
});

function companyBoxes() {
  return within(screen.getByTestId("company-filters")).getAllByRole("checkbox") as HTMLInputElement[];
}

describe("发现岗位的企业筛选", () => {
  it("点击「全部」全选所有公司，再点一次取消全选", async () => {
    render(<JobDiscoveryPanel />);
    await waitFor(() => expect(api.getOfficialSources).toHaveBeenCalled());

    // 默认只勾选 P0 公司，所以「全部」是可点的全选入口。
    const boxes = companyBoxes();
    expect(boxes.length).toBeGreaterThan(1);
    expect(boxes.every((box) => box.checked)).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "全部" }));
    await waitFor(() => expect(companyBoxes().every((box) => box.checked)).toBe(true));

    const toggleOff = screen.getByRole("button", { name: "取消全部" });
    expect(toggleOff).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(toggleOff);
    await waitFor(() => expect(companyBoxes().every((box) => !box.checked)).toBe(true));
    expect(screen.getByRole("button", { name: "全部" })).toBeInTheDocument();
  });

  it("手动取消一个公司后，「全部」按钮回到未全选状态", async () => {
    render(<JobDiscoveryPanel />);
    await waitFor(() => expect(api.getOfficialSources).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "全部" }));
    await waitFor(() => expect(companyBoxes().every((box) => box.checked)).toBe(true));

    fireEvent.click(companyBoxes()[0]!);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "全部" })).toBeInTheDocument(),
    );
  });

  it("按企业一键核验全部候选：数量来自后端，点击后进入后台任务", async () => {
    api.getPendingLeadCount.mockResolvedValue({ ok: true, data: { count: 14 } });
    api.startLeadVerification.mockResolvedValue({
      ok: true,
      data: { run_id: "run-leads", status: "queued", reused: false },
    });
    api.getJobMaintenance.mockResolvedValue({
      ok: true,
      data: {
        id: "run-leads",
        kind: "verify_leads",
        status: "running",
        progress: { total: 14, processed: 3, current: "大模型算法工程师" },
        result: {},
        error_message: null,
        created_at: "2026-11-16T06:00:00Z",
        started_at: "2026-11-16T06:00:01Z",
        finished_at: null,
      },
    });

    render(<JobDiscoveryPanel />);
    fireEvent.click(screen.getByRole("button", { name: /搜索|发现/ }));
    await screen.findByText("候选岗位链接");

    const button = await screen.findByRole("button", { name: /候选（14 条）/ });
    // The button opens the scope chooser; 「全选」starts without a limit.
    fireEvent.click(button);
    fireEvent.click(await screen.findByRole("button", { name: /开始核验全部 14 条/ }));

    await waitFor(() => expect(api.startLeadVerification).toHaveBeenCalled());
    const [labels, limit] = api.startLeadVerification.mock.calls[0] ?? [];
    expect((labels as string[]).length).toBeGreaterThan(0);
    expect(limit).toBeUndefined();
    expect(await screen.findByText(/正在核验 3 \/ 14/)).toBeVisible();
  });

  it("自定义数量只核验指定的条数", async () => {
    api.getPendingLeadCount.mockResolvedValue({ ok: true, data: { count: 14 } });
    api.startLeadVerification.mockResolvedValue({
      ok: true,
      data: { run_id: "run-custom", status: "queued", reused: false },
    });
    api.getJobMaintenance.mockResolvedValue({
      ok: true,
      data: {
        id: "run-custom",
        kind: "verify_leads",
        status: "queued",
        progress: { total: 5, processed: 0, current: null },
        result: {},
        error_message: null,
        created_at: "2026-11-16T06:00:00Z",
        started_at: null,
        finished_at: null,
      },
    });

    render(<JobDiscoveryPanel />);
    fireEvent.click(screen.getByRole("button", { name: /搜索|发现/ }));
    await screen.findByText("候选岗位链接");

    fireEvent.click(await screen.findByRole("button", { name: /候选（14 条）/ }));
    fireEvent.click(await screen.findByRole("radio", { name: /自定义/ }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: /开始核验 5 条/ }));

    await waitFor(() =>
      expect(api.startLeadVerification).toHaveBeenCalledWith(expect.any(Array), 5),
    );
  });
});
