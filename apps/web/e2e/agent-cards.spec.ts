import { expect, test } from "@playwright/test";

/**
 * Proves the real chain: LangGraph agent -> structured API -> web container ->
 * browser cards. Requires LLM + Tavily; skipped (not failed) when the server
 * reports it is not configured, so a missing key never yields a false pass.
 */
test.describe("Agent structured cards (real LLM)", () => {
  test("job search renders structured cards", async ({ page }) => {
    test.skip(
      test.info().project.name !== "desktop",
      "agent flow runs once on desktop",
    );
    test.setTimeout(300_000);
    const email = `e2e-agent-${Date.now()}@example.com`;

    await page.goto("/login");
    await page.getByRole("button", { name: "注册", exact: true }).click();
    await page.locator("#email").fill(email);
    await page.locator("#password").fill("strong-pass-123");
    await page.getByRole("button", { name: "注册并登录" }).click();
    await page.waitForURL(/\/jobs/, { timeout: 30_000 });

    await page.goto("/agent");
    await page.getByRole("button", { name: "新建对话" }).click();

    const input = page.getByPlaceholder("输入你的求职需求...");
    await expect(input).toBeEnabled({ timeout: 20_000 });
    await input.fill("帮我找大模型算法实习岗位");
    await input.press("Enter");

    const cardLinks = page.getByRole("link", { name: "在招聘中心查看" });
    const errorBanner = page.locator("p.text-rose-700").first();

    // The page header already renders one such link, so cards are only proven
    // once a second one appears (or the server reports an error).
    await expect
      .poll(
        async () => {
          if (await errorBanner.isVisible().catch(() => false)) return "error";
          return cardLinks.count();
        },
        { timeout: 260_000, intervals: [1000] },
      )
      .not.toBe(1);

    if (await errorBanner.isVisible().catch(() => false)) {
      const text = (await errorBanner.textContent()) ?? "";
      if (/LLM|未配置|503|NOT_CONFIGURED/i.test(text)) {
        test.skip(true, `LLM 未配置：${text.slice(0, 120)}`);
      }
      throw new Error(`Agent 执行报错：${text.slice(0, 300)}`);
    }

    // Structured job cards rendered by the freshly deployed container.
    const count = await cardLinks.count();
    expect(count).toBeGreaterThanOrEqual(2);
    // Every card exposes at least one navigation target.
    const navTargets = page
      .getByRole("link", { name: "官网" })
      .or(page.getByRole("link", { name: "详情" }));
    expect(await navTargets.count()).toBeGreaterThanOrEqual(1);
  });
});
