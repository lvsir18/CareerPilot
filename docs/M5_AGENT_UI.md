# M5.2 Agent 结构化结果卡片

> 日期：2026-10-23

## 1. 数据来源（不使用正则解析 Markdown）

```
专业 Agent 子图执行
    ↓
ToolMessage（工具真实返回的 JSON）
    ↓
Supervisor._execute 收集 tool_results[{agent, tool, data}]
    ↓
AgentService._structure_tool_results() 按工具类型归类
    ↓
API 返回 structured: { jobs, matches, applications, progress_events }
    ↓
前端 /agent 渲染卡片
```

工具返回值本身来自 M1–M4 的真实 Service（JobDiscoveryService / RecommendationService /
ApplicationService），因此卡片内容与可视化页面同源，不由 LLM 生成。

## 2. 结构化映射

| 工具 | 归类 | 字段 |
|---|---|---|
| `search_jobs` | `jobs` | jobs + leads（含 id/company/title/city/source_url/verification_status） |
| `get_job_detail` | `jobs` | 单岗位详情 |
| `recommend_jobs` | `matches` | items[{job, match, applied_status}] |
| `match_job` | `matches` | 单条匹配 |
| `list_applications` | `applications` | 申请记录 |
| `get_application_timeline` | `progress_events` | 事件时间线 |

## 3. 前端交互

`/agent` 在自然语言回答下方渲染：

- **岗位卡片**：公司/岗位/城市/类型 + 核验状态 + 「官网」「详情」「在招聘中心查看」
- **匹配卡片**：匹配分数（仅来自 MatchingService）、资格状态、命中技能、未体现技能、官网/详情
- **申请卡片**：公司/岗位/状态 + 「查看申请详情」→ `/applications/{id}`

跳转 `/discover?q=` 保留搜索条件。

## 4. 约束

- 未重写 M4 Supervisor / 专业 Agent / Tool 定义
- 未使用正则解析 Agent 文本
- 前端不生成匹配分数，只展示 `match.match_score`
- 无结构化结果时退回纯文本展示（兼容旧会话）

## 5. 未完成

- 卡片未复用现有 `JobCard` 组件（为避免 Agent 区域样式耦合，使用了轻量内联卡片）
- 未展示 Tool 调用的逐步执行轨迹（M4 的 plan 已在 API 返回，前端尚未渲染）
- 未对 `progress_events` 做时间线可视化
