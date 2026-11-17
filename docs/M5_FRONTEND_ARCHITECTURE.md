# M5 前端架构与页面结构

> 日期：2026-10-22
> 状态：M5-A/B/C/D/E/F 核心闭环已实现；部分深度交互为第一版简化实现。

## 1. 导航结构

左侧导航（`components/app-shell.tsx`）：

| 导航 | 路由 | 说明 |
|---|---|---|
| 求职总览 | `/dashboard` | 8 项真实统计 + 最新招聘 + 最近进度 + 即将开始 |
| 招聘信息 | `/discover` | 多企业/城市/类型/方向筛选、卡片/表格 |
| 岗位推荐 | `/matches` | M3 heuristic_v1 匹配结果 |
| 我的收藏 | `/saved-jobs` | SavedJob 真实数据 |
| 面试日程 | `/calendar` | ApplicationEvent 真实事件 |
| 导入岗位 | `/import` | 官方链接/JD 导入 |
| 简历管理 | `/resumes` | PDF/DOCX 解析 |
| 我的画像 | `/profile` | 画像确认与偏好 |
| Agent 工作台 | `/agent` | M4 LangGraph 会话 |
| 投递看板 | `/applications` | 列表/表格/看板三视图 |
| 设置 | — | M6 |

## 2. 页面与数据来源

| 页面 | 数据来源 |
|---|---|
| `/dashboard` | `GET /api/v1/dashboard/summary`（聚合 SavedJob/Application/ApplicationEvent/ApplicationImport/Job） |
| `/discover` | `GET /api/v1/jobs/discover`（Tavily + 本地库 + 诊断） |
| `/saved-jobs` | `GET /api/v1/saved-jobs` |
| `/calendar` | `dashboard/summary` 的 upcoming/recent events |
| `/applications` | `GET /api/v1/applications` + `GET /api/v1/saved-jobs?list_type=to_apply` |
| `/applications/[id]` | `GET /api/v1/applications/{id}` |
| `/matches` | `GET /api/v1/matches/recommendations` |
| `/agent` | `POST /api/v1/agent/threads/{id}/runs` |

## 3. 新增/修改组件

- `app/(app)/dashboard/page.tsx`：重做为真实数据工作台
- `app/(app)/saved-jobs/page.tsx`：新增
- `app/(app)/calendar/page.tsx`：新增
- `app/(app)/applications/[id]/page.tsx`：新增申请详情
- `app/(app)/applications/page.tsx`：新增 list/table/kanban 三视图
- `components/job-discovery-panel.tsx`：新增 URL 筛选持久化、卡片/表格切换、询问 Agent
- `components/email-import-panel.tsx`：新增批量 .eml 多选与逐条结果
- `lib/client-api.ts` / `lib/api.ts`：新增 dashboard、批量导入、Agent 联动类型与函数

## 4. 交互状态

- Loading：同步执行时按钮 disabled + 文案
- Empty：各页面独立空状态
- Error：API 失败展示 `error.message`
- Partial：批量导入逐条显示成功/重复/失败
- Data Stale：JD/来源状态明确标注“待核验”
- 不把缓存结果伪装成实时搜索

## 5. 复用约定

- 不新增重复业务数据库；全部复用 M1–M4 模型与 Service
- 收藏、申请、匹配、Agent 共享同一 API 与用户身份
- 官网链接统一 `target="_blank" rel="noreferrer noopener"`
