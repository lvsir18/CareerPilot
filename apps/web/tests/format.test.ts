import { describe, expect, it } from "vitest";

import { formatDateTime } from "@/lib/format";

describe("formatDateTime", () => {
  it("缺少时间时显示未知，不推断发布日期", () => {
    expect(formatDateTime(null)).toBe("未知");
    expect(formatDateTime(undefined)).toBe("未知");
  });

  it("无法解析的时间显示未知", () => {
    expect(formatDateTime("not-a-date")).toBe("未知");
  });

  it("按指定时区格式化 ISO 时间", () => {
    const formatted = formatDateTime("2026-10-21T05:00:00Z", "Asia/Shanghai");

    expect(formatted).toContain("2026");
    expect(formatted).toMatch(/13:00/);
  });

  describe("跨时区显示（同一 UTC 时刻）", () => {
    const utc = "2026-10-25T06:00:00Z";

    it("Asia/Shanghai 为 UTC+8", () => {
      expect(formatDateTime(utc, "Asia/Shanghai")).toMatch(/2026\/10\/25.*14:00/);
    });

    it("Asia/Singapore 与上海同为 UTC+8", () => {
      expect(formatDateTime(utc, "Asia/Singapore")).toMatch(/2026\/10\/25.*14:00/);
    });

    it("UTC 保持原时刻", () => {
      expect(formatDateTime(utc, "UTC")).toMatch(/2026\/10\/25.*06:00/);
    });

    it("America/New_York 夏令时为 UTC-4", () => {
      expect(formatDateTime(utc, "America/New_York")).toMatch(/2026\/10\/25.*02:00/);
    });
  });

  describe("日期边界归属", () => {
    // 20:00Z → 上海次日 04:00，纽约当日 16:00
    const lateUtc = "2026-10-25T20:00:00Z";

    it("东八区跨入次日", () => {
      expect(formatDateTime(lateUtc, "Asia/Shanghai")).toMatch(/2026\/10\/26/);
    });

    it("UTC 仍在当日", () => {
      expect(formatDateTime(lateUtc, "UTC")).toMatch(/2026\/10\/25/);
    });

    it("纽约仍在当日", () => {
      expect(formatDateTime(lateUtc, "America/New_York")).toMatch(/2026\/10\/25.*16:00/);
    });
  });

  describe("美国夏令时切换", () => {
    it("2026-11-01 DST 结束前后相差一小时", () => {
      const before = formatDateTime("2026-11-01T05:30:00Z", "America/New_York");
      const after = formatDateTime("2026-11-01T06:30:00Z", "America/New_York");

      expect(before).toMatch(/01:30/);
      expect(after).toMatch(/01:30/);
    });

    it("2026-03-08 DST 开始前后相差一小时", () => {
      const before = formatDateTime("2026-03-08T06:30:00Z", "America/New_York");
      const after = formatDateTime("2026-03-08T07:30:00Z", "America/New_York");

      expect(before).toMatch(/01:30/);
      expect(after).toMatch(/03:30/);
    });
  });
});
