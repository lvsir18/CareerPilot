import { beforeEach, describe, expect, it } from "vitest";

import { DRAFT_PREFIX, clearAllProfileDrafts, draftKey } from "@/lib/profile-draft";

describe("画像草稿按账号隔离", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("不同账号写入不同的键", () => {
    expect(draftKey("user-a")).not.toBe(draftKey("user-b"));
    expect(draftKey("user-a").startsWith(DRAFT_PREFIX)).toBe(true);
  });

  it("退出时清空所有草稿，不把上一账号内容留给下一账号", () => {
    sessionStorage.setItem(draftKey("user-a"), "A 的未保存草稿");
    sessionStorage.setItem(draftKey("user-b"), "B 的未保存草稿");
    sessionStorage.setItem("careerpilot.other", "keep-me");

    clearAllProfileDrafts();

    expect(sessionStorage.getItem(draftKey("user-a"))).toBeNull();
    expect(sessionStorage.getItem(draftKey("user-b"))).toBeNull();
    // Unrelated client state is not touched.
    expect(sessionStorage.getItem("careerpilot.other")).toBe("keep-me");
  });
});
