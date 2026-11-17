import { expect, test, type Page, type Route } from "@playwright/test";

// These browser regressions use controlled run/SSE responses. They test the
// real router and UI without depending on LLM timing or writing fictional jobs.
async function accountAndThread(page: Page, project: string): Promise<string> {
  await page.goto("/login");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await page.locator("#email").fill(`e2e-regression-${project}-${Date.now()}@example.com`);
  await page.locator("#password").fill("strong-pass-123");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await page.waitForURL(/\/jobs/);
  const csrf = (await page.context().cookies()).find((c) => c.name === "careerpilot_csrf")!.value;
  // The Next proxy only serves GET/SSE; writes use the backend like client-api.
  const response = await page.request.post(`${process.env.E2E_API_BASE_URL ?? "http://localhost:8000"}/api/v1/agent/threads`, {
    headers: { Origin: new URL(page.url()).origin, "X-CSRF-Token": csrf },
    data: { title: "历史线程" },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()).data.id;
}
function completedRun(threadId: string, answer: string) {
  return {
    id: "00000000-0000-4000-8000-000000000001", thread_id: threadId,
    request_id: "controlled-browser-regression", status: "completed",
    error_code: null, error_summary: null, created_at: new Date().toISOString(),
    started_at: null, finished_at: null, cancel_requested_at: null, attempt_count: 1,
    result: {
      thread_id: threadId, status: "completed", intent: "profile_query", constraints: {},
      plan: [], agent_results: {}, errors: [], final_answer: answer,
      structured: { jobs: [], matches: [], applications: [], progress_events: [], extra_matches: [] as object[] },
    },
  };
}

test("late messages from an old thread cannot hide the new completed answer", async ({ page }, info) => {
  const oldThread = await accountAndThread(page, info.project.name);
  let delayed: Route | undefined;
  await page.route(`**/api/v1/agent/threads/${oldThread}/messages`, (route) => { delayed = route; });
  await page.route("**/api/v1/agent/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const body = route.request().postDataJSON();
    const run = completedRun(body.thread_id, "新会话已完成（受控响应）");
    await route.fulfill({ status: 202,
      headers: { "access-control-allow-origin": new URL(page.url()).origin, "access-control-allow-credentials": "true" },
      json: { data: { ...run, status: "queued", result: null } } });
  });
  await page.route("**/api/v1/agent/runs/*/stream", async (route) => {
    const threadId = new URL(page.url()).searchParams.get("thread")!;
    const run = completedRun(threadId, "新会话已完成（受控响应）");
    await route.fulfill({
      status: 200, contentType: "text/event-stream",
      body: `id: 1\nevent: run.final\ndata: ${JSON.stringify({ sequence: 1, status: "completed", result: run.result })}\n\n`,
    });
  });
  await page.goto(`/agent?thread=${oldThread}`);
  await expect(page.getByText("正在加载会话…", { exact: true })).toBeVisible();
  const menu = page.getByRole("button", { name: "打开会话列表", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("button", { name: "新建对话", exact: true }).click();
  await page.getByPlaceholder("输入你的求职需求...").fill("立即发送新问题");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText("新会话已完成（受控响应）", { exact: true })).toBeVisible();
  await expect(page.getByText("正在加载会话…", { exact: true })).toHaveCount(0);
  expect(delayed).toBeDefined();
  await delayed!.fulfill({ json: { data: [{ role: "assistant", content: "迟到旧消息" }] } });
  await expect(page.getByText("迟到旧消息", { exact: true })).toHaveCount(0);
  await expect(page.getByText("新会话已完成（受控响应）", { exact: true })).toBeVisible();
});

test("extra candidates remain inspectable when all matches are excluded", async ({ page }, info) => {
  const threadId = await accountAndThread(page, info.project.name);
  const run = completedRun(threadId, "没有符合本轮方向的岗位（受控响应）");
  run.result.structured.extra_matches = [{
    job: { id: "controlled-candidate", company: "测试企业", title: "未入选候选示例" },
    match: { match_score: 25 }, selection_reason: "不在本轮限定的岗位方向",
  }];
  await page.route(`**/api/v1/agent/threads/${threadId}/runs?*`, (route) =>
    route.fulfill({ json: { data: [run] } }));
  await page.goto(`/agent?thread=${threadId}`);
  const summary = page.getByText("另有 1 个候选未列入本轮条件", { exact: true });
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(page.getByText(/测试企业 · 未入选候选示例/)).toBeVisible();
});
