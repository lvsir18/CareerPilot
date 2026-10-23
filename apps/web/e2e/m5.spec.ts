import { expect, test } from "@playwright/test";

function uniqueEmail(project: string): string {
  return `e2e-${project}-${Date.now()}@example.com`;
}

async function assertNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => {
    const el = document.documentElement;
    return el.scrollWidth - el.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(2);
}

test("register + core pages render on this viewport", async ({ page }, testInfo) => {
  const email = uniqueEmail(testInfo.project.name);

  // 1) 真实浏览器注册并登录
  await page.goto("/login");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.locator("#email").fill(email);
  await page.locator("#password").fill("strong-pass-123");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await page.waitForURL(/\/jobs/, { timeout: 30_000 });

  // 2) Dashboard
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "求职工作台" })).toBeVisible();
  await expect(page.getByText("已收藏岗位")).toBeVisible();
  await assertNoHorizontalOverflow(page);

  // 3) Discover（只验证筛选 UI，不触发外部 Tavily）
  await page.goto("/discover");
  await expect(page.getByRole("heading", { name: "发现官方岗位" })).toBeVisible();
  await expect(page.getByPlaceholder("如 Agent 实习")).toBeVisible();
  await expect(page.getByRole("button", { name: "发现岗位" })).toBeEnabled();
  await assertNoHorizontalOverflow(page);

  // 4) Applications（默认列表 + 切换链接存在）
  await page.goto("/applications");
  await expect(page.getByRole("heading", { name: "个人申请进度" })).toBeVisible();
  await expect(page.getByRole("link", { name: "看板", exact: true })).toBeAttached();
  await assertNoHorizontalOverflow(page);

  // 5) Calendar
  await page.goto("/calendar");
  await expect(page.getByRole("heading", { name: "面试日程" })).toBeVisible();
  await expect(page.getByRole("button", { name: "月" })).toBeVisible();
  await assertNoHorizontalOverflow(page);

  // 6) 邮箱设置
  await page.goto("/settings/email");
  await expect(page.getByRole("heading", { name: "邮箱同步" })).toBeVisible();
  await expect(page.getByText("绑定 QQ 邮箱")).toBeVisible();
  await expect(page.getByText("绑定 Gmail")).toBeVisible();
  await assertNoHorizontalOverflow(page);
});

test("job detail opens from job list", async ({ page }, testInfo) => {
  const email = uniqueEmail(`${testInfo.project.name}-detail`);

  await page.goto("/login");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.locator("#email").fill(email);
  await page.locator("#password").fill("strong-pass-123");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await page.waitForURL(/\/jobs/, { timeout: 30_000 });

  const firstJob = page.locator('a[href^="/jobs/"]').first();
  if ((await firstJob.count()) === 0) {
    test.skip(true, "当前没有已核验岗位，跳过岗位详情流程");
  }
  await firstJob.click();
  await page.waitForURL(/\/jobs\/[0-9a-f-]+/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await assertNoHorizontalOverflow(page);
});
