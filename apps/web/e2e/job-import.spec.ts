import { expect, test } from "@playwright/test";

async function register(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.locator("#email").fill(`jd-e2e-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`);
  await page.locator("#password").fill("strong-pass-123");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await page.waitForURL(/\/jobs$/);
  await page.goto("/import");
}

test("完整JD草稿经真实保存后仍保留职责与最后一项要求", async ({ page }) => {
  await register(page);
  const description = "岗位职责\n【自动化测试】负责开发与代码评审。";
  const requirements = ["熟悉Java。", "末项要求：掌握RAG。"];
  const additional_info = "在招业务\nToken Foundry";
  await page.route("**/api/v1/job-imports/preview-link", route => route.fulfill({ json: { data: {
    url: "https://campus.163.com/app/detail/index?id=e2e", final_url: "https://campus.163.com/app/detail/index?id=e2e",
    title: "【自动化测试】JD完整性回归", company: "网易", city: "杭州", location_text: "杭州",
    job_type: "campus", description, requirements, additional_info, warnings: [], source: "rendered",
  } } }));
  await page.getByLabel("官方岗位链接", { exact: true }).fill("https://campus.163.com/app/detail/index?id=e2e");
  await expect(page.getByRole("button", { name: "确认并入库", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "解析页面", exact: true }).click();
  await expect(page.getByLabel("职位描述（必填）")).toHaveValue(description);
  await expect(page.getByLabel("任职要求（每行一条）")).toHaveValue(requirements.join("\n"));
  await expect(page.getByLabel("其他岗位信息（业务、福利等）")).toHaveValue(additional_info);
  await expect(page.getByLabel("岗位类型", { exact: true })).toHaveValue("campus");
  await expect(page.getByLabel("官方岗位链接", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
  await page.getByRole("button", { name: "保存为私有候选", exact: true }).click();
  await page.waitForURL(/\/leads\/[0-9a-f-]+$/);
  await expect(page.getByText("末项要求：掌握RAG。", { exact: false })).toBeVisible();
  await expect(page.getByText(/Token Foundry/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "【自动化测试】JD完整性回归", exact: true })).toBeVisible();
});

test("换链接和解析失败会清理旧草稿，手动模式仍可填写URL", async ({ page }) => {
  await register(page);
  await page.getByRole("button", { name: "粘贴 JD（任意企业）", exact: true }).click();
  await page.getByLabel("官方岗位链接", { exact: true }).fill("https://example.com/detail/1");
  await page.getByLabel("岗位名称", { exact: true }).fill("旧岗位");
  await page.getByLabel("职位描述（必填）").fill("旧岗位正文");
  await page.route("**/api/v1/job-imports/preview-link", route => route.fulfill({ status: 422,
    json: { error: { code: "LINK_PREVIEW_FAILED", message: "页面未能读取JD，请手动补充" } },
  }));
  await page.getByLabel("官方岗位链接", { exact: true }).fill("https://example.com/detail/2");
  await page.getByRole("button", { name: "解析页面", exact: true }).click();
  await expect(page.getByText(/页面未能读取JD/)).toBeVisible();
  await expect(page.getByLabel("岗位名称", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("职位描述（必填）")).toHaveValue("");
  await expect(page.getByRole("button", { name: "保存为私有候选", exact: true })).toBeDisabled();
});
