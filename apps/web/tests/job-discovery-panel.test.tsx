import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobDiscoveryPanel } from "@/components/job-discovery-panel";

const api = vi.hoisted(() => ({
  discoverJobs: vi.fn(),
  getOfficialSources: vi.fn(),
  searchOfficialJobs: vi.fn(),
  verifyJobLead: vi.fn(),
}));

vi.mock("@/lib/client-api", async (original) => ({ ...(await original<object>()), ...api }));

beforeEach(() => {
  vi.clearAllMocks();
  api.getOfficialSources.mockResolvedValue({ ok: true, data: [] });
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
});
