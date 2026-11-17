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

// The manual keeps all chapter content available while search narrows navigation.
describe("手册查找与截图", () => {
  it("搜索正文可定位到操作小节，清空后恢复目录", async () => {
    const { fireEvent, within } = await import("@testing-library/react");
    render(<GuidePage />);
    const nav = screen.getByRole("navigation", { name: "手册目录" });
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索手册" }), { target: { value: "协作式" } });
    expect(within(nav).getByRole("link", { name: /执行与中断/ })).toHaveAttribute("href", "#agent-run");
    expect(within(nav).queryByRole("link", { name: "页面地图" })).toBeNull();
    expect(document.getElementById("pages")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
    expect(within(nav).getByRole("link", { name: "页面地图" })).toBeInTheDocument();
  });

  it("无匹配时给出提示，手机目录可展开并在跳转后收起", async () => {
    const { fireEvent } = await import("@testing-library/react");
    render(<GuidePage />);
    const toggle = screen.getByRole("button", { name: /章节目录/ });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索手册" }), { target: { value: "zzzz-no-match" } });
    expect(screen.getByRole("status")).toHaveTextContent("找到 0 个相关章节");
    expect(screen.getByText(/没有找到结果/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
    const nav = screen.getByRole("navigation", { name: "手册目录" });
    fireEvent.click(nav.querySelector('a[href="#profile"]')!);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("上下文截图具有替代文字、原图入口与演示说明", () => {
    render(<GuidePage />);
    expect(screen.getByRole("img", { name: "演示岗位推荐" })).toHaveAttribute("src", "/guide/matches.png");
    expect(screen.getByRole("link", { name: "查看大图：Agent 预置演示对话" })).toHaveAttribute("href", "/guide/agent.png");
    expect(screen.getAllByText(/虚构演示数据/).length).toBeGreaterThan(1);
  });
});

describe("公开手册复用", () => {
  it("公开模式保留章节跳转、重写业务入口并支持 Pages 图片前缀", async () => {
    const { GuideReader } = await import("@/components/guide-reader");
    render(<GuideReader publicSite assetPrefix="/CareerPilot" />);
    expect(screen.getByRole("link", { name: /第一次部署/ })).toHaveAttribute("href", "#start");
    const operationLinks = screen.getAllByRole("link", { name: "查看操作说明 →" });
    expect(operationLinks.length).toBeGreaterThan(0);
    for (const link of operationLinks) expect(link.getAttribute("href")).toMatch(/^#/);
    expect(screen.getByRole("img", { name: "演示岗位推荐" })).toHaveAttribute("src", "/CareerPilot/guide/matches.png");
    expect(screen.getByRole("link", { name: "回到首页" })).toHaveAttribute("href", "/");
  });
});
