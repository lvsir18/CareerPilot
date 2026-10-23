export type MilestoneStatus = "done" | "next" | "planned";

export interface Milestone {
  id: string;
  title: string;
  status: MilestoneStatus;
  items: string[];
}

/**
 * Delivery roadmap copied from the specification. This is product scope,
 * not job data, so rendering it is safe in demo and production modes.
 */
export const MILESTONES: Milestone[] = [
  {
    id: "M0",
    title: "项目初始化与基础工程",
    status: "done",
    items: ["Next.js + FastAPI 骨架", "Docker Compose 编排", "统一错误与结构化日志", "Lint / Test 基线"],
  },
  {
    id: "M1",
    title: "数据库、认证与核心业务模型",
    status: "next",
    items: ["SQLAlchemy 模型与 Alembic 迁移", "注册登录与用户隔离", "岗位查询与收藏 CRUD", "Demo 数据 seed"],
  },
  {
    id: "M2",
    title: "招聘数据连接器与同步",
    status: "planned",
    items: ["Connector 协议与去重", "公开 ATS 连接器", "同步日志与源健康"],
  },
  {
    id: "M3",
    title: "简历画像与可解释匹配",
    status: "planned",
    items: ["PDF / DOCX 解析", "用户确认画像", "heuristic_v1 评分"],
  },
  {
    id: "M4",
    title: "LangGraph 多 Agent 工作流",
    status: "planned",
    items: ["Supervisor 路由", "结构化事件流", "运行持久化与恢复"],
  },
  {
    id: "M5",
    title: "Agent Workspace 与投递看板",
    status: "planned",
    items: ["任务时间线", "待投递清单", "手动投递状态"],
  },
  {
    id: "M6",
    title: "集成、E2E 与部署交付",
    status: "planned",
    items: ["Playwright E2E", "安全与迁移回归", "部署文档"],
  },
];
