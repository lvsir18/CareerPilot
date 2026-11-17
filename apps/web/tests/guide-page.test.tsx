import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import GuidePage from "@/app/(app)/guide/page";
import { GUIDE_SECTIONS } from "@/lib/guide-content";

const ANCHORS: [string, string][] = [
  ["what", "它能做什么，不做什么"],
  ["start", "快速开始（自部署）"],
  ["pages", "页面地图"],
  ["account", "账号与登录"],
  ["profile", "简历与画像"],
  ["discover", "找岗位：发现与核验"],
  ["import", "导入岗位"],
  ["jobs", "岗位库与维护"],
  ["matches", "推荐与匹配"],
  ["applications", "投递与面试"],
  ["agent", "Agent 工作台"],
  ["keys", "模型与搜索 Key（按账号隔离）"],
  ["mobile", "手机与多端访问"],
  ["config", "配置速查"],
  ["faq", "常见问题"],
  ["limits", "限制、边界与路线图"],
];

describe("使用手册页", () => {
  it("渲染标题与全部章节锚点", () => {
    render(<GuidePage />);

    expect(screen.getByRole("heading", { level: 1, name: /从注册到拿到面试/ })).toBeVisible();

    for (const [id, label] of ANCHORS) {
      expect(screen.getAllByRole("link", { name: label }).length).toBeGreaterThan(0);
      expect(document.getElementById(id)).not.toBeNull();
    }
  });

  it("每个章节都有内容，不再是空壳", () => {
    for (const section of GUIDE_SECTIONS) {
      const blocks = section.blocks?.length ?? 0;
      const subs = section.subsections?.reduce((sum, item) => sum + item.blocks.length, 0) ?? 0;
      expect(blocks + subs).toBeGreaterThan(0);
    }
  });

  it("覆盖关键操作说明", () => {
    render(<GuidePage />);

    // 部署
    expect(screen.getAllByText(/docker compose up -d/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/ADMIN_EMAILS/).length).toBeGreaterThan(0);
    // 账号
    expect(screen.getAllByText(/忘记密码/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Argon2id/).length).toBeGreaterThan(0);
    // 岗位维护
    expect(screen.getAllByText(/最久没检查的优先/).length).toBeGreaterThan(0);
    expect(screen.getByText(/职位已下架 \/ 招聘已结束/)).toBeVisible();
    // 多轮追问
    expect(screen.getAllByText(/那杭州呢/).length).toBeGreaterThan(0);
    // Key
    expect(screen.getAllByText(/sk-ab…9f2c/).length).toBeGreaterThan(0);
    // 多端
    expect(screen.getAllByText(/同一 Wi-Fi/).length).toBeGreaterThan(0);
  });

  it("说明边界，不承诺自动投递", () => {
    render(<GuidePage />);

    expect(screen.getByText(/不自动投递/)).toBeVisible();
    expect(screen.getByText(/没有 PWA \/ 原生 App/)).toBeVisible();
  });
});
