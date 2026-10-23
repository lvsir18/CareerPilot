import type { StatusTone } from "@/components/status-pill";

const JOB_TYPE_LABELS: Record<string, string> = {
  internship: "实习",
  campus: "校招",
  full_time: "全职",
  part_time: "兼职",
  contract: "合同制",
  unknown: "类型未知",
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  fixture: "演示数据源",
  manual: "人工录入",
  greenhouse_public: "Greenhouse",
  lever_public: "Lever",
  ashby_public: "Ashby",
  approved_company_site: "企业官网",
  baidu_public: "百度招聘官网",
  tavily_extract: "Tavily 官方详情提取",
};

export function formatSourceType(value: string): string {
  return SOURCE_TYPE_LABELS[value] ?? value;
}

const JOB_STATUS_LABELS: Record<string, string> = {
  open: "开放",
  closed: "已关闭",
  unknown: "状态未知",
};

export function formatJobType(value: string | null | undefined): string {
  if (!value) {
    return "类型未知";
  }
  return JOB_TYPE_LABELS[value] ?? value;
}

const JOB_FAMILY_LABELS: Record<string, string> = {
  llm_agent: "LLM / Agent",
  algorithm_data: "算法 / 数据",
  backend: "后端 / 基础架构",
  frontend: "前端 / 客户端",
  product: "产品",
  design: "设计",
  operations: "运营 / 综合",
  other: "其他",
};

export function formatJobFamily(value: string | null | undefined): string {
  return value ? JOB_FAMILY_LABELS[value] ?? value : "方向未知";
}

export function formatJobStatus(value: string): string {
  return JOB_STATUS_LABELS[value] ?? value;
}

export function jobStatusTone(value: string): StatusTone {
  if (value === "open") {
    return "ok";
  }
  if (value === "closed") {
    return "neutral";
  }
  return "warning";
}

const VERIFICATION_LABELS: Record<string, string> = {
  verified: "官方页面已核验",
  user_confirmed: "用户已确认",
  unverified: "未核验",
  stale: "核验已过期",
};

export function formatVerificationStatus(value: string): string {
  return VERIFICATION_LABELS[value] ?? value;
}

export function verificationTone(value: string): StatusTone {
  if (value === "verified" || value === "verified_official") {
    return "ok";
  }
  if (value === "user_confirmed" || value === "user_provided") {
    return "info";
  }
  if (value === "stale" || value === "search_snippet_only") {
    return "warning";
  }
  return "neutral";
}

const LEAD_STATUS_LABELS: Record<string, string> = {
  verified_official: "官方已核验",
  user_provided: "用户导入",
  search_snippet_only: "待核验",
  stale: "核验已过期",
};

export function formatLeadStatus(value: string): string {
  return LEAD_STATUS_LABELS[value] ?? value;
}

const APPLICATION_STATUS_LABELS: Record<string, string> = {
  saved: "已收藏",
  planned: "计划申请",
  to_apply: "待投递",
  preparing: "准备中",
  applied: "已申请",
  screening: "简历筛选中",
  assessment: "笔试/测评",
  online_assessment: "笔试",
  interview: "面试",
  offer: "Offer",
  rejected: "未通过/结束",
  withdrawn: "已撤回",
  closed: "已结束",
  unknown: "未知",
};

export const APPLICATION_STATUS_OPTIONS = [
  "saved",
  "planned",
  "applied",
  "screening",
  "assessment",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
  "unknown",
  "to_apply",
  "preparing",
  "online_assessment",
  "closed",
] as const;

export function formatApplicationStatus(value: string): string {
  return APPLICATION_STATUS_LABELS[value] ?? value;
}

const APPLICATION_SOURCE_LABELS: Record<string, string> = {
  manual: "用户登记",
  email_import: "邮件导入",
  official_api: "官方 API",
  browser_assisted: "浏览器辅助",
  user_manual: "用户登记",
};

export function formatApplicationSource(value: string | null | undefined): string {
  if (!value) {
    return "未知来源";
  }
  return APPLICATION_SOURCE_LABELS[value] ?? value;
}

const EVENT_VERIFICATION_LABELS: Record<string, string> = {
  user_reported: "用户填报",
  email_confirmed: "邮件佐证",
  website_user_confirmed: "用户官网确认",
  official_api: "官方 API",
  unverified: "未核验",
};

export function formatEventVerification(value: string): string {
  return EVENT_VERIFICATION_LABELS[value] ?? value;
}
