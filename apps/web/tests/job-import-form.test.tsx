import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { JobImportForm } from "@/components/job-import-form";

const api = vi.hoisted(() => ({
  previewJobImport: vi.fn(), previewJobLink: vi.fn(), importJobLead: vi.fn(), importJob: vi.fn(),
}));
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("@/lib/client-api", () => api);
vi.mock("next/navigation", () => ({ useRouter: () => router }));
afterEach(cleanup);
beforeEach(() => { vi.clearAllMocks(); });
const draft = {
  url: "https://campus.163.com/app/detail/index?id=1", final_url: "https://campus.163.com/app/detail/index?id=1",
  title: "Java开发工程师", company: "网易", city: "杭州", location_text: "杭州",
  job_type: "campus", description: "岗位描述：负责开发。", requirements: ["熟悉Java。", "最后一项RAG。"], additional_info: "在招业务\nToken Foundry", warnings: [], source: "rendered",
};
function fillUrl(url: string) {
  fireEvent.change(screen.getByLabelText("官方岗位链接"), { target: { value: url } });
}
it("浏览器草稿保留完整正文与真实岗位类型，保存为私有候选", async () => {
  api.previewJobLink.mockResolvedValue({ ok: true, data: draft });
  api.importJobLead.mockResolvedValue({ ok: true, data: { id: "private-lead" } });
  render(<JobImportForm />); fillUrl(draft.url);
  fireEvent.click(screen.getByRole("button", { name: "解析页面" }));
  await waitFor(() => expect(screen.getByLabelText("岗位类型")).toHaveValue("campus"));
  expect(screen.getByLabelText("职位描述（必填）")).toHaveValue(draft.description);
  expect(screen.getByLabelText("任职要求（每行一条）")).toHaveValue(draft.requirements.join("\n"));
  expect(screen.getByLabelText("其他岗位信息（业务、福利等）")).toHaveValue(draft.additional_info);
  expect(api.previewJobImport).not.toHaveBeenCalled();
  expect(screen.getByLabelText("官方岗位链接")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "保存为私有候选" }));
  await waitFor(() => expect(api.importJobLead).toHaveBeenCalledWith(expect.objectContaining({
    description: `${draft.description}\n\n任职要求：\n${draft.requirements.join("\n")}\n\n${draft.additional_info}`, job_type: "campus", title: draft.title,
  })));
  expect(router.push).toHaveBeenCalledWith("/leads/private-lead");
});
it("换链接后不继承上一个岗位的公司、类型或正文，失败后不允许误保存", async () => {
  api.previewJobLink.mockResolvedValueOnce({ ok: true, data: draft })
    .mockResolvedValueOnce({ ok: true, data: { ...draft, company: null, title: "AI工程师", job_type: null, city: null } })
    .mockResolvedValueOnce({ ok: false, error: { message: "没有读到JD" } });
  render(<JobImportForm />); fillUrl(draft.url);
  fireEvent.click(screen.getByRole("button", { name: "解析页面" }));
  await screen.findByLabelText("公司");
  fillUrl("https://another.example.com/detail/2");
  expect(screen.getByLabelText("公司")).toHaveValue("");
  expect(screen.getByLabelText("职位描述（必填）")).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: "解析页面" }));
  await waitFor(() => expect(screen.getByLabelText("岗位名称")).toHaveValue("AI工程师"));
  expect(screen.getByLabelText("公司")).toHaveValue("");
  expect(screen.getByLabelText("岗位类型")).toHaveValue("unknown");
  fillUrl("https://another.example.com/detail/3");
  fireEvent.click(screen.getByRole("button", { name: "解析页面" }));
  await screen.findByText(/没有读到JD/);
  expect(screen.getByRole("button", { name: "保存为私有候选" })).toBeDisabled();
});
it("手动粘贴模式仍提供链接输入，不会出现无法填写链接和保存的死路", () => {
  render(<JobImportForm />);
  fireEvent.click(screen.getByRole("button", { name: "粘贴 JD（任意企业）" }));
  fireEvent.change(screen.getByLabelText("职位描述（必填）"), { target: { value: "先粘贴的JD" } });
  fillUrl("https://example.com/detail/1");
  expect(screen.getByLabelText("职位描述（必填）")).toHaveValue("先粘贴的JD");
  expect(screen.getByLabelText("官方岗位链接")).toBeVisible();
  expect(screen.getByLabelText("岗位类型")).toHaveValue("unknown");
});
it("百度预览展示专用解析器的任职要求", async () => {
  api.previewJobImport.mockResolvedValue({ ok: true, data: {
    source_url: "https://talent.baidu.com/jobs/detail/INTERN/id", source_job_id: "id", title: "开发实习生", company: "百度",
    description: "开发测试工具", requirements: ["熟悉Python", "最后要求：每周四天"], warnings: [],
  } });
  render(<JobImportForm />); fillUrl("https://talent.baidu.com/jobs/detail/INTERN/id");
  fireEvent.click(screen.getByRole("button", { name: "解析页面" }));
  await screen.findByText("开发实习生");
  expect(screen.getByText(/最后要求：每周四天/)).toBeInTheDocument();
  expect(api.previewJobLink).not.toHaveBeenCalled();
});
