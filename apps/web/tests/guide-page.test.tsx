import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import GuidePage from "@/app/(app)/guide/page";

const ANCHORS: [string, string][] = [
  ["start", "五分钟上手"],
  ["pages", "页面地图"],
  ["account", "账号与登录"],
  ["resume", "简历与画像"],
  ["jobs", "找岗位"],
  ["maintain", "维护岗位库"],
  ["match", "推荐与匹配"],
  ["apply", "投递与面试"],
  ["agent", "Agent 工作台"],
  ["keys", "模型与搜索 Key"],
  ["mobile", "手机与多端"],
  ["limits", "限制与边界"],
];

describe("使用手册页", () => {
  it("渲染标题与全部章节锚点", () => {
    render(<GuidePage />);

    expect(screen.getByRole("heading", { level: 1, name: /从注册到拿到面试/ })).toBeVisible();

    for (const [id, label] of ANCHORS) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", `#${id}`);
      expect(document.getElementById(id)).not.toBeNull();
    }
  });

  it("覆盖关键操作说明", () => {
    render(<GuidePage />);

    // 账号（「忘记密码」在章节与提示中各出现一次）
    expect(screen.getAllByText(/忘记密码/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Argon2id/)).toBeVisible();
    // 岗位维护
    expect(screen.getByText(/最久未检查优先/)).toBeVisible();
    expect(screen.getByText(/职位已下架 \/ 招聘已结束/)).toBeVisible();
    // 多轮追问
    expect(screen.getByText("「那杭州呢」")).toBeVisible();
    expect(screen.getByText("「刚才找到几个」")).toBeVisible();
    // Key
    expect(screen.getByText(/sk-ab…9f2c/)).toBeVisible();
    // 多端
    expect(screen.getAllByText(/同一 Wi-Fi/).length).toBeGreaterThan(0);
  });

  it("说明边界，不承诺自动投递", () => {
    render(<GuidePage />);

    expect(screen.getByText(/不自动投递、不自动填表/)).toBeVisible();
    expect(screen.getByText(/没有 PWA \/ 原生 App/)).toBeVisible();
  });
});
