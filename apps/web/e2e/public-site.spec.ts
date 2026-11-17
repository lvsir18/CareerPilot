import { expect, test } from "@playwright/test";

test("public site works anonymously under the Pages project path", async ({ page }) => {
  const errors: string[] = [];
  const apiRequests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => { if (new URL(request.url()).pathname.startsWith("/api/")) apiRequests.push(request.url()); });
  await page.goto("./");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("让每一步求职");
  await expect(page.getByRole("img", { name: /CareerPilot 岗位库/ })).toBeVisible();
  for (const name of ["个人画像", "可解释匹配", "Agent 助手", "投递看板", "面试日程", "岗位库"]) {
    const button = page.getByRole("button", { name, exact: true });
    await button.click();
    await expect(button).toHaveAttribute("aria-pressed", "true");
    const image = page.getByRole("img", { name: `${name}界面，虚构演示数据` });
    await expect.poll(() => image.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("navigation", { name: "站点导航" }).getByRole("link", { name: "用户手册" }).click();
  await expect(page).toHaveURL(/\/CareerPilot\/guide\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("从注册到拿到面试");
  await page.getByRole("link", { name: /第一次部署/ }).click();
  await expect(page).toHaveURL(/#start$/);
  if ((page.viewportSize()?.width ?? 1440) < 1024) await page.getByRole("button", { name: /章节目录/ }).click();
  await page.getByRole("searchbox", { name: "搜索手册" }).fill("协作式");
  await page.getByRole("navigation", { name: "手册目录" }).getByRole("link", { name: /执行与中断/ }).click();
  await expect(page).toHaveURL(/#agent-run$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  for (const image of await page.locator("main figure img").all()) {
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
    expect(await image.getAttribute("src")).toMatch(/^\/CareerPilot\/guide\//);
  }
  const brokenRoutes = await page.locator('main a[href^="/"]').evaluateAll((links) => links.map((link) => link.getAttribute("href")).filter((href) => !href?.startsWith("/CareerPilot/")));
  expect(brokenRoutes).toEqual([]);
  await page.getByRole("navigation", { name: "站点导航" }).getByRole("link", { name: "本地部署" }).click();
  await expect(page).toHaveURL(/\/CareerPilot\/start\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("搭建你的求职工作台");
  await expect(page.locator("pre")).toContainText("alembic upgrade head");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
});
