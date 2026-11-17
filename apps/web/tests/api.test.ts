import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchReadiness, fetchSystemInfo } from "@/lib/api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchReadiness", () => {
  it("就绪时返回依赖检查与检查时间", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          status: "ready",
          checks: [
            { name: "database", status: "ok", detail: null },
            { name: "redis", status: "ok", detail: null },
          ],
          checked_at: "2026-10-21T05:00:00Z",
        }),
      ),
    );

    const snapshot = await fetchReadiness();

    expect(snapshot.reachable).toBe(true);
    expect(snapshot.ready).toBe(true);
    expect(snapshot.checks).toHaveLength(2);
    expect(snapshot.checkedAt).toBe("2026-10-21T05:00:00Z");
    expect(snapshot.error).toBeNull();
  });

  it("503 时保留各个依赖的检查明细", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "DEPENDENCY_UNAVAILABLE",
              message: "关键依赖未就绪",
              details: {
                checks: [
                  { name: "database", status: "ok", detail: null },
                  { name: "redis", status: "error", detail: "unreachable" },
                ],
              },
            },
          },
          503,
        ),
      ),
    );

    const snapshot = await fetchReadiness();

    expect(snapshot.reachable).toBe(true);
    expect(snapshot.ready).toBe(false);
    expect(snapshot.error?.code).toBe("DEPENDENCY_UNAVAILABLE");
    expect(snapshot.checks.find((check) => check.name === "redis")?.status).toBe("error");
  });

  it("网络异常时标记为不可达而不是抛出", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    const snapshot = await fetchReadiness();

    expect(snapshot.reachable).toBe(false);
    expect(snapshot.ready).toBe(false);
    expect(snapshot.checks).toEqual([]);
    expect(snapshot.error?.code).toBe("NETWORK_ERROR");
  });
});

describe("fetchSystemInfo", () => {
  it("解析运行模式", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          app_name: "CareerPilot API",
          version: "0.1.0",
          app_env: "development",
          demo_mode: true,
          execution_mode: "rule_fallback",
          llm_configured: false,
          public_connectors_enabled: false,
          job_sync_enabled: false,
          api_docs_url: "http://localhost:8000/docs",
        }),
      ),
    );

    const result = await fetchSystemInfo();

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.execution_mode).toBe("rule_fallback");
      expect(result.data.demo_mode).toBe(true);
    }
  });

  it("使用统一错误信封", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: "INTERNAL_ERROR", message: "服务器内部错误", details: {} } }, 500),
      ),
    );

    const result = await fetchSystemInfo();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.code).toBe("INTERNAL_ERROR");
      expect(result.error.status).toBe(500);
    }
  });

  it("字段缺失时不把响应当作有效数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ app_name: "CareerPilot" })));

    const result = await fetchSystemInfo();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.code).toBe("UNEXPECTED_RESPONSE");
    }
  });
});
