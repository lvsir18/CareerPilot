import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/(app)/path/to/user

describe("首页介绍", () => {
  it("展示定位、四块能力与主要入口", () => {
    render(<HomePage />);

    expect(screen.getByText(/把求职从/)).toBeVisible();
    for (const title of [
      "官方核验的岗位库",
      "可解释的画像匹配",
      "能追问的求职 Agent",
      "投递与面试时间线",
    ]) {
      expect(screen.getByText(title)).toBeVisible();
    }

    expect(screen.getByRole("link", { name: /进入岗位库/ })).toHaveAttribute("href", "/jobs");
    expect(screen.getByRole("link", { name: /打开 Agent 工作台/ })).toHaveAttribute(
      "href",
      "/agent",
    );
    expect(screen.getByRole("link", { name: /查看我的概览/ })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("写明边界，不承诺自动投递", () => {
    render(<HomePage />);

    expect(screen.getByText(/不自动投递、不自动填表/)).toBeVisible();
    expect(screen.getByText(/不保存招聘平台密码/)).toBeVisible();
  });
});
