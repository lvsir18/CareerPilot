import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SystemStatusPanel } from "@/components/system-status-panel";
import type { ReadinessSnapshot } from "@/lib/api";

function snapshot(overrides: Partial<ReadinessSnapshot> = {}): ReadinessSnapshot {
  return {
    reachable: true,
    ready: true,
    checks: [
      { name: "database", status: "ok", detail: null },
      { name: "redis", status: "ok", detail: null },
    ],
    checkedAt: "2026-10-21T05:00:00Z",
    error: null,
    ...overrides,
  };
}

describe("SystemStatusPanel", () => {
  it("全部依赖正常时显示就绪状态", () => {
    render(<SystemStatusPanel readiness={snapshot()} />);

    expect(screen.getByText("依赖就绪")).toBeInTheDocument();
    expect(screen.getAllByText("正常")).toHaveLength(3);
    expect(screen.getByText("数据库")).toBeInTheDocument();
    expect(screen.getByText("Redis")).toBeInTheDocument();
  });

  it("依赖异常时显示错误状态与错误码", () => {
    render(
      <SystemStatusPanel
        readiness={snapshot({
          ready: false,
          checks: [
            { name: "database", status: "ok", detail: null },
            { name: "redis", status: "error", detail: "unreachable" },
          ],
          checkedAt: null,
          error: { code: "DEPENDENCY_UNAVAILABLE", message: "关键依赖未就绪" },
        })}
      />,
    );

    expect(screen.getByText("依赖异常")).toBeInTheDocument();
    expect(screen.getByText("不可用")).toBeInTheDocument();
    expect(screen.getByText("DEPENDENCY_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("检查时间：未知")).toBeInTheDocument();
  });

  it("API 不可达时三个服务都标记为不可用", () => {
    render(
      <SystemStatusPanel
        readiness={snapshot({
          reachable: false,
          ready: false,
          checks: [],
          checkedAt: null,
          error: { code: "NETWORK_ERROR", message: "无法连接 API 服务" },
        })}
      />,
    );

    expect(screen.getByText("API 不可达")).toBeInTheDocument();
    expect(screen.getByText("无法连接")).toBeInTheDocument();
    // Database and Redis were never reached, so their state stays "未检测".
    expect(screen.getAllByText("未检测")).toHaveLength(2);
    expect(screen.getByText("NETWORK_ERROR")).toBeInTheDocument();
  });
});
