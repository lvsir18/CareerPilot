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
  manual_import: "私有 JD 导入",
  greenhouse_public: "Greenhouse",
  lever_public: "Lever",
  ashby_public: "Ashby",
  approved_company_site: "企业官网",
  baidu_public: "百度招聘官网",
  tavily_extract: "Tavily 官方详情提取",
  tencent_campus: "腾讯校招官网",
  tencent_campus_rendered: "腾讯校招官网",
  bytedance_campus_rendered: "字节跳动校招官网",
  xiaohongshu_campus_rendered: "小红书校招官网",
  bilibili_campus_rendered: "哔哩哔哩校招官网",
  meituan_campus_rendered: "美团校招官网",
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

const AGENT_RUN_STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  waiting_for_user: "等待你确认",
  completed: "已完成",
  partial: "部分完成（有步骤失败）",
  failed: "执行失败",
  cancelled: "已取消",
  timed_out: "已超时",
};

export function formatAgentRunStatus(value: string | null | undefined): string {
  if (!value) {
    return "未开始";
  }
  return AGENT_RUN_STATUS_LABELS[value] ?? value;
}

const AGENT_EVENT_LABELS: Record<string, string> = {
  "run.queued": "任务已排队",
  "run.started": "开始执行",
  "run.resumed": "继续执行",
  "plan.created": "已生成计划",
  "agent.started": "子任务开始",
  "agent.completed": "子任务完成",
  "tool.started": "调用工具",
  "tool.completed": "工具返回",
  "approval.required": "需要你确认",
  "run.completed": "执行完成",
  "run.partial": "部分完成",
  "run.failed": "执行失败",
  "run.cancelled": "已取消",
  "run.final": "结果已生成",
};

export function formatAgentEventType(value: string): string {
  return AGENT_EVENT_LABELS[value] ?? value;
}

const ELIGIBILITY_LABELS: Record<string, string> = {
  eligible: "符合资格",
  likely_eligible: "较可能符合",
  unclear: "信息不足",
  ineligible: "不符合资格",
  unknown: "未判断",
};

export function formatEligibility(value: string | null | undefined): string {
  if (!value) {
    return "未判断";
  }
  return ELIGIBILITY_LABELS[value] ?? value;
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
