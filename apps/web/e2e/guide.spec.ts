import { expect, test } from "@playwright/test";

test("guide navigation, search and illustrations work at every viewport", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.locator("#email").fill(`guide-${info.project.name}-${Date.now()}@example.com`);
  await page.locator("#password").fill("guide-test-only-123");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await page.waitForURL(/\/(jobs|home)(?:\?|$)/);
  await page.goto("/guide");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("从注册到拿到面试");
  const mobile = (page.viewportSize()?.width ?? 1440) < 1024;
  const toggle = page.getByRole("button", { name: /章节目录/ });
  if (mobile) await toggle.click();
  const search = page.getByRole("searchbox", { name: "搜索手册" });
  await search.fill("协作式");
  await page.getByRole("navigation", { name: "手册目录" }).getByRole("link", { name: /执行与中断/ }).click();
  await expect(page).toHaveURL(/#agent-run$/);
  if (mobile) {
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    const top = await page.locator("#agent-run").evaluate((el) => el.getBoundingClientRect().top);
    const directoryBottom = await toggle.evaluate((el) => el.getBoundingClientRect().bottom);
    expect(top).toBeGreaterThanOrEqual(directoryBottom + 8);
    await toggle.click();
  }
  await search.fill("no-matching-guide-topic");
  await expect(page.getByRole("status")).toContainText("找到 0 个相关章节");
  await page.getByRole("button", { name: "清空搜索" }).click();
  await expect(page.getByRole("navigation", { name: "手册目录" }).getByRole("link", { name: "页面地图", exact: true })).toBeVisible();
  if (mobile) await toggle.click();
  for (const image of await page.locator("main figure img").all()) {
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
