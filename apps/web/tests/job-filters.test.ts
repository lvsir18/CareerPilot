import { describe, expect, it } from "vitest";

import {
  buildJobQuery,
  DEFAULT_JOB_FILTERS,
  jobPageHref,
  parseJobFilters,
} from "@/lib/job-filters";

describe("parseJobFilters", () => {
  it("空参数使用安全默认值", () => {
    expect(parseJobFilters(undefined)).toEqual(DEFAULT_JOB_FILTERS);
    expect(parseJobFilters({})).toEqual(DEFAULT_JOB_FILTERS);
  });

  it("丢弃非法排序与页码", () => {
    const filters = parseJobFilters({ sort: "drop_table", page: "-2" });

    expect(filters.sort).toBe("published_at_desc");
    expect(filters.page).toBe(1);
  });

  it("支持数组形式的 query 参数", () => {
    const filters = parseJobFilters({ q: ["Agent", "ignored"], page: "3" });

    expect(filters.q).toBe("Agent");
    expect(filters.page).toBe(3);
  });
});

describe("buildJobQuery", () => {
  it("省略空条件并保留分页信息", () => {
    const query = buildJobQuery({ ...DEFAULT_JOB_FILTERS, page: 2 }, 12);
    const params = new URLSearchParams(query);

    expect(params.get("page_size")).toBe("12");
    expect(params.get("page")).toBe("2");
    expect(params.has("q")).toBe(false);
    expect(params.has("sort")).toBe(false);
  });

  it("去除首尾空格并保留多值城市", () => {
    const query = buildJobQuery({
      ...DEFAULT_JOB_FILTERS,
      q: "  Agent  ",
      cities: "北京,上海",
      job_types: "internship",
      sort: "first_seen_at_desc",
    });
    const params = new URLSearchParams(query);

    expect(params.get("q")).toBe("Agent");
    expect(params.get("cities")).toBe("北京,上海");
    expect(params.get("job_types")).toBe("internship");
    expect(params.get("sort")).toBe("first_seen_at_desc");
  });

  it("生成可复制的分页链接", () => {
    expect(jobPageHref({ ...DEFAULT_JOB_FILTERS, q: "Agent" }, 3, 12)).toBe(
      "/jobs?q=Agent&page=3&page_size=12",
    );
  });
});
