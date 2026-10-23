import { describe, expect, it } from "vitest";

import {
  formatApplicationStatus,
  formatJobStatus,
  formatJobType,
  formatLeadStatus,
  formatSourceType,
  formatVerificationStatus,
  jobStatusTone,
  verificationTone,
} from "@/lib/job-display";

describe("岗位展示映射", () => {
  it("未知字段不会伪装成已知", () => {
    expect(formatJobType(null)).toBe("类型未知");
    expect(formatJobType("unknown")).toBe("类型未知");
    expect(formatJobStatus("unknown")).toBe("状态未知");
  });

  it("来源类型可读", () => {
    expect(formatSourceType("fixture")).toBe("演示数据源");
    expect(formatSourceType("manual")).toBe("人工录入");
    expect(formatSourceType("custom_source")).toBe("custom_source");
  });

  it("状态颜色区分开放与未知", () => {
    expect(jobStatusTone("open")).toBe("ok");
    expect(jobStatusTone("closed")).toBe("neutral");
    expect(jobStatusTone("unknown")).toBe("warning");
  });

  it("核验状态与真实来源标识可读", () => {
    expect(formatSourceType("baidu_public")).toBe("百度招聘官网");
    expect(formatVerificationStatus("verified")).toBe("官方页面已核验");
    expect(formatVerificationStatus("user_confirmed")).toBe("用户已确认");
    expect(verificationTone("verified")).toBe("ok");
    expect(verificationTone("user_confirmed")).toBe("info");
    expect(verificationTone("unverified")).toBe("neutral");
  });

  it("候选链接状态不会被标成官方已核验", () => {
    expect(formatLeadStatus("search_snippet_only")).toBe("待核验");
    expect(formatLeadStatus("user_provided")).toBe("用户导入");
    expect(formatLeadStatus("verified_official")).toBe("官方已核验");
    expect(verificationTone("search_snippet_only")).toBe("warning");
    expect(verificationTone("user_provided")).toBe("info");
    expect(verificationTone("verified_official")).toBe("ok");
  });
});

describe("投递状态映射", () => {
  it("覆盖手动状态枚举", () => {
    expect(formatApplicationStatus("to_apply")).toBe("待投递");
    expect(formatApplicationStatus("online_assessment")).toBe("笔试");
    expect(formatApplicationStatus("interview")).toBe("面试");
    expect(formatApplicationStatus("offer")).toBe("Offer");
  });

  it("未知值原样展示而不是猜测", () => {
    expect(formatApplicationStatus("custom_status")).toBe("custom_status");
  });
});
