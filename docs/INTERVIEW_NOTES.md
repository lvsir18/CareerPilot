# CareerPilot 项目复盘（面试用）

> 面向 Agent / 后端 / 全栈岗位的面试材料：技术栈、整体架构、子系统设计、项目亮点、踩坑记录与常见追问。
>
> 数据截至 2026-10-26，取自仓库实际代码与提交历史（`git log` 33 次提交、16 个 Alembic 迁移）。

---

## 0. 一句话定位与规模

**CareerPilot**：面向求职者的 AI 求职副驾驶。主链路是「简历 → 结构化画像 → 岗位发现与匹配 → 投递进度 → 面试日程」，
其上提供一个基于 LangGraph 的多 Agent 工作台。

设计上有一条贯穿始终的约束：**岗位必须来自可追溯的来源**（官方接口 / 官方页面渲染 / 用户显式确认），
Agent 只做检索与解释，**不做自动投递、不托管平台账号密码**。

| 指标 | 数量 |
|---|---|
| 后端 Python | 20,650 行（`backend/app`） |
| 后端测试 | 8,322 行，**326 passed** |
| 前端 TS/TSX | 11,062 行 |
| REST 接口 | **89** 个 |
| 数据表 / 迁移 | **16** 张 / **16** 个 |
| Agent 结构 | 1 Supervisor + 4 专业 Agent + **10** 个受限工具 |
| 官方直连企业 | **7** 家（腾讯、京东、字节、小红书、B站、美团、MiniMax） |
| 企业目录 | **19** 家；岗位方向 **14** 类 |
| 前端单测 | Vitest **40 passed** + Playwright e2e |

---

## 1. 技术栈详解

### 1.1 Web 与校验层

| 技术 | 用途 | 选型理由 |
|---|---|---|
| **FastAPI 0.156** | 全部 REST + SSE | 原生 async；依赖注入承担鉴权与 DB 会话；OpenAPI 自动生成；SSE 直接用 `StreamingResponse` |
| **Pydantic v2** | 请求/响应模型、配置 | Rust 内核校验；`Field(max_length)` 约束"形状" |
| **uvicorn[standard]** | ASGI Server | 生产可用，支持多 worker |

**分层原则**：Pydantic 管"形状"，Service 管"业务规则"。
例：手动进度事件接口禁止 `browser_assisted` 来源，这条用模型 validator 表达，因为它是**契约**；
而"预约改期只能替换同类型"属于**流程**，放在 Service 并用行锁保护。

### 1.2 数据层

| 技术 | 用途 | 关键点 |
|---|---|---|
| **PostgreSQL** | 主库 + Agent 检查点 + 事件表 | JSONB 存画像/解析结果；`CREATE INDEX CONCURRENTLY` 建检查点索引；行级锁 |
| **SQLAlchemy 2.1** | ORM | 全量 2.0 风格（`select()` / `scalars()`），无 legacy Query |
| **Alembic** | 16 个迁移 | 每个功能都带迁移，测试会真实执行升级链路 |

**为什么预约用软作废而不是删除**：时间线需要保留"这场面试被改期过"的历史，
所以用 `superseded_at` 标记失效，日历按"未作废"过滤，历史仍可追溯。

### 1.3 异步与调度

| 技术 | 用途 |
|---|---|
| **Celery 5.6 + Redis** | Agent run 执行、岗位来源同步、邮箱增量同步 |
| **Celery Beat** | 定时扇出（`sync_enabled_sources`、`sync_enabled_mailboxes`） |

三个工程约束：

- **幂等**：`request_id` 相同直接返回已有 run；同步任务按来源 + 时间窗去重；
- **防并发**：`claim()` 用行锁抢占，同一来源/邮箱不会重叠执行；
- **超时**：Agent 任务 `soft_time_limit=240 / time_limit=300`，避免单任务占满 worker。

### 1.4 Agent 层

| 技术 | 用途 | 说明 |
|---|---|---|
| **LangGraph 1.2** | 状态图编排 | `StateGraph` + 条件边，Supervisor 路由到 4 个子 Agent |
| **PostgresSaver** | 检查点持久化 | 进程重启可续跑；HITL 中断依赖它 |
| **langchain-core** | 模型调用抽象 | 只用 chat model 与 tool 绑定，不引入重框架 |

**为什么不用 AgentExecutor 黑盒**：需要确定性的路由、可中断可恢复、可取消、可回放，
这四点用显式图节点更好落地。

### 1.5 数据采集层

| 技术 | 用途 |
|---|---|
| **httpx** | 官方 JSON 接口（腾讯、京东）、Tavily 调用 |
| **Playwright 1.64** | 渲染型招聘站、任意链接解析 |
| **Tavily** | 搜索索引（线索）+ Extract（详情核验） |
| **PyMuPDF / python-docx** | 简历 PDF/DOCX 文本提取 |
| **cryptography** | 邮箱凭据加密（`MAILBOX_SECRET_KEY`） |

### 1.6 前端

| 技术 | 用途 |
|---|---|
| **Next.js 16 App Router + RSC** | 14 个页面路由，服务端渲染首屏 |
| **React 19 + TypeScript 5.9** | 严格类型，`tsc --noEmit` 进流程 |
| **Tailwind v4** | 设计系统，无第三方 UI 库 |
| **SSE** | Agent 实时进度（`fetch` 流 + `Last-Event-ID` 续传） |
| **Vitest + Playwright** | 组件单测 + 关键路径 e2e |

### 1.7 工程化

- **ruff**（E/F/I/B/UP/SIM/C4/RUF，line-length 100）、**eslint 10**、**tsc --noEmit**；
- **pytest** 326 用例，含需要真实 PostgreSQL 的 integration 用例；
- **Docker Compose** 五服务（api / web / worker / postgres / redis），`make smoke` 做外部服务冒烟；
- 文档沉淀：架构、评估、安全评审、备份恢复、逐轮用户测试报告与证据截图。

---

## 2. 整体架构

### 2.1 分层

```
┌────────────────────────── apps/web (Next.js) ──────────────────────────┐
│ 页面(RSC) · 客户端组件 · client-api(fetch/CSRF/超时) · SSE 订阅         │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ HTTPS + HttpOnly Cookie + CSRF
┌───────────────────────────────▼────────────────────────────────────────┐
│                        FastAPI (api/v1, 89 端点)                       │
│ auth · profile · resumes · jobs · job-imports · job-leads · saved      │
│ applications · application-imports · job-sources · matches · dashboard │
│ mailboxes · recruitment-email-candidates · agent · agent/runs · system │
└──────┬──────────────────┬───────────────────────┬──────────────────────┘
       │                  │                       │
┌──────▼──────┐  ┌────────▼─────────┐  ┌──────────▼───────────┐
│  Service 层 │  │  Agent 层        │  │ Search/Connector 层   │
│ 业务规则/事务│  │ Supervisor+4子图 │  │ httpx / Playwright    │
│             │  │ 10 受限工具      │  │ Tavily / 简历解析     │
└──────┬──────┘  └────────┬─────────┘  └──────────┬───────────┘
       │                  │                       │
┌──────▼──────────────────▼───────────────────────▼──────────┐
│ PostgreSQL(业务表 + 检查点 + 事件表)   Redis(Celery)   Worker │
└────────────────────────────────────────────────────────────┘
```

### 2.2 一次提问的完整链路

```
POST /agent/runs
  ├─ 建 AgentRun(queued)，request_id 幂等
  └─ Celery .delay() → worker

worker:
  claim() 行锁抢占 → 载入 LangGraph 检查点
    → supervisor.plan → 路由到子 Agent(检索/匹配/画像/进度)
    → 受限工具调用（每次调用前检查取消）
    → _aggregate 按约束拆分 matches / extra_items
    → 每个节点边界：ensure_active() + emit(event) + commit

前端:
  GET /agent/runs/{id}/stream (SSE)
    ├─ 每帧 id:<sequence>
    └─ 断线重连带 Last-Event-ID → events_after(sequence) 续播
```

### 2.3 数据模型（16 张表，按域分组）

| 域 | 表 | 关键设计 |
|---|---|---|
| 身份 | `users`、`user_sessions` | Argon2 密码、HttpOnly Cookie、CSRF 双提交 |
| 求职资产 | `resumes`、`candidate_profiles`、`job_preferences` | 解析结果存 JSONB；画像带 `version` 与 `verified_by_user` |
| 岗位 | `jobs`、`job_leads`、`saved_jobs`、`job_sources`、`sync_runs` | `(source_id, source_job_id)` 唯一；`content_hash` 判变化；`last_checked_at` 记录确认时间 |
| 进度 | `applications`、`application_events`、`application_imports` | 事件带 `is_scheduled`（是否占日历）与 `superseded_at`（改期留痕） |
| Agent | `agent_threads`、`agent_runs`、`agent_run_events` | 事件 `sequence` 单调，支撑 SSE 续传 |
| 邮箱 | `mailbox_connections`、`recruitment_event_candidates`、`external_account_connections` | 凭据加密；同步只产"待确认候选" |

### 2.4 关键数据流：从"发现"到"入库"

```
搜索(线索) ──► JobLead(候选, 可私有) ──核验──► Job(可检索, 带来源证据)
官方直连 ─────────────────────────────► Job(带 JD, 来源 *_rendered / *_campus)
粘贴 JD ──────────────────────────────► JobLead(私有, 标记 user_provided)
```

只有进入 `jobs` 的岗位参与高精度匹配；只有链接的候选不参与打分，避免"用标题猜 JD"。

---

## 3. Agent 子系统

### 3.1 为什么是 Supervisor + 专业 Agent

单 Agent 塞 10 个工具会造成上下文污染（检索结果混进进度问答）。拆成 4 个子 Agent：

| 子 Agent | 职责 | 绑定工具 |
|---|---|---|
| `job_search` | 找岗位、看详情、导入候选 | search_jobs / get_job_detail / get_job_leads / import_official_jobs |
| `job_match` | 推荐与单岗匹配 | recommend_jobs / match_job |
| `profile` | 画像摘要 | get_profile_summary |
| `progress` | 投递进度与日程 | list_applications / get_application_timeline / check_job_application_status |

Supervisor 只做计划与汇总，**不直接调工具**，避免它把结果当常识编造。

### 3.2 工具是"受限"的

- 只读或可追溯写入：没有自动投递、自动填表、平台账号托管；
- 参数强校验：无法识别的标识返回 `IDENTIFIER_NOT_RECOGNIZED`，**不猜**；
- 输出带北京时间标签（`starts_at_label`）与三种 id（`application_id` / `job_id` / `source_job_id`）；
- 每次工具调用前 `ensure_active()`，取消立即生效。

### 3.3 状态卫生：会话级 vs 轮次级

真实 bug：第二轮问答会把第一轮的 `tool_results` 当本轮结果。修复方式是在入口重置轮次级状态：

```python
def _understand(state):
    state["tool_results"] = {}   # 每轮重置
    state["agent_results"] = []
    state["errors"] = []
    state["final_answer"] = ""
```

**结论**：Agent 状态不是"越全越好"，要区分「会话级」（画像、约束）与「轮次级」（工具结果）。

### 3.4 LLM 输出用数据结构约束

问题：用户选了"只看上海"，模型却推荐了北京岗位。

方案：在代码里做约束拆分，而不是只依赖提示词。

- `_split_matches(items, constraints)` 产出 `matches` 与 `extra_items`（带 `selection_reason`）；
- 提示词只允许引用 `matches`；为空时必须明说"没有符合条件的岗位"；
- 前端把 `extra_items` 折叠成「另有 N 个候选未列入本轮条件」。

**结论**：LLM 的约束要落在数据结构上，不能只靠"请遵守"。

### 3.5 异步 + SSE + 断线续传

- `agent_runs` 存状态，`agent_run_events` 存事件（`sequence` 单调）；
- SSE 每帧带 `id: <sequence>`；浏览器重连自动带 `Last-Event-ID`；
- 后端优先读请求头，其次 `?lastEventId=`，从 `sequence > N` 续播；
- 隐蔽坑：SQLAlchemy 会话缓存导致 `run.final` 永远读不到 → `populate_existing=True` 强制刷新。

### 3.6 取消是状态机终态，不是信号

强杀 worker 会留下半写状态。实现上：取消只置 `cancel_requested_at`；
图在**节点边界**与**每次工具调用前**检查，抛 `RunCancelled`，统一落到 `cancelled` 并补一条事件。

### 3.7 HITL：中断要持久化，恢复要重新鉴权

画像未确认时，匹配工具返回 `PROFILE_NOT_CONFIRMED`，run 进入 `waiting_for_user` 并推一张确认卡片。

- 用户确认后 `POST /agent/threads/{id}/resume`；
- 后端**再次校验** `verified_by_user`，通过才置 `queued` 并 `.delay()`；
- 未通过则保持 `waiting`，不消耗 token。

---

## 4. 数据采集子系统

### 4.1 三层来源

| 层级 | 方式 | 代表 | 成本 / 稳定性 |
|---|---|---|---|
| L1 | 官方 JSON 接口 | 腾讯、京东 | ~2s，稳，无签名 |
| L2 | 无头浏览器渲染 | 字节、小红书、B站、美团、MiniMax | ~15s，较脆，随对方改版失效 |
| L3 | 搜索索引 + 详情核验 | Tavily | 只给线索，需用户确认或核验 |

### 4.2 为什么必须用浏览器

字节 `_signature`、小红书 `x-s/x-s-common`、B站 `ajSessionId` 都由前端 JS 生成且会轮换，
服务端 replay 不可维护；httpx 直取只能得到空壳 HTML。做法：

```
打开官方公共搜索页
  → 监听 response，只取 application/json
  → 在 JSON 里按"标题/ID/JD 字段"打分找最像岗位数组的结构
  → 键名容错表映射成统一 RawJob
```

关键词不能只靠 `?keyword=`（SPA 多半忽略），要**打进站内搜索框**再捕获请求，
否则会出现"看起来有结果、其实没按关键词搜"的隐蔽问题。

### 4.3 通用链接解析与 SSRF 防护

用户粘任意企业链接 → 服务端浏览器打开。这等于开放"替用户访问任意 URL"的能力，因此：

- 仅 `http/https`、仅 80/443、禁止 URL 内嵌凭据；
- 域名解析出的**所有 IP 必须是公网**（拒绝 `127.0.0.1`、`10.x`、`169.254.169.254`）；
- **重定向后二次校验**；
- 一次一页，不翻页、不登录、不绕验证码；
- 解析结果只是**草稿**，用户确认后才入库并标记"用户导入"。

### 4.4 去重与"没抓到 ≠ 下架"

- 唯一键 `(source_id, source_job_id)`；`content_hash` 判断 JD 是否变化；`last_checked_at` 记录最近确认；
- 代码中明确：抓取里没出现不等于岗位关闭，只有来源显式给状态才改 `status`；
- 原因：关键词没覆盖、分页没翻到、对方 503 都会造成"没出现"。

---

## 5. 项目亮点

| # | 亮点 | 问题 → 方案 → 取舍 |
|---|---|---|
| 1 | 异步 Agent + 可续传 SSE | 长任务阻塞请求 → run/事件双表 + `Last-Event-ID`；牺牲实现简单换取"刷新不丢进度" |
| 2 | 协作式取消 | 强杀留脏状态 → 检查点 + 终态收敛；牺牲"立即停止"换数据一致 |
| 3 | LLM 输出用代码约束 | 提示词不可靠 → 结构化 `matches/extra_items`；牺牲模型自由度换不误导用户 |
| 4 | 画像闸门 + 可恢复 HITL | 未确认画像导致匹配无意义 → 409 + 卡片 + resume 重鉴权 |
| 5 | 三层采集、官方优先 | 聚合站数据不可信 → API/渲染/搜索分级，来源可追溯 |
| 6 | SSRF 硬防护 | 任意 URL 解析危险 → 公网校验 + 重定向复检 + 单次读取 |
| 7 | 简历解析按章节切分 | 原实现把奖项/日期当标题 → 章节闭合 + 日期锚点 + 标题回溯，实习与项目分栏 |
| 8 | 可解释匹配 | 黑盒分数无意义 → 技能/方向/城市/资格分项 + 证据行 |
| 9 | 面试日程语义正确 | "投递"不该进日历 → 只有显式预约才展示；改期不叠加、取消留痕 |
| 10 | 证据驱动迭代 | 33 次提交中大量"用户测试报告 → 缺陷 → 修复 → 归档证据" |

---

## 6. 踩坑与解决

| 问题 | 根因 | 修复 |
|---|---|---|
| 多轮问答串结果 | 检查点残留上一轮 `tool_results` | 入口按轮重置 |
| 取消后仍写入 | 取消只在入口检查一次 | 节点边界 + 每次工具调用前检查，抛 `RunCancelled` |
| SSE 收不到 `run.final` | SQLAlchemy 会话缓存读旧行 | `populate_existing=True` |
| 轮询与 SSE 互相污染 | 双数据源同时 setState，旧响应覆盖新状态 | `loadToken` 代次 + `isStale` 判定 |
| HITL 被绕过 | resume 未重新校验画像 | 409 + 保持 `waiting` |
| 改期后旧预约仍显示 | 新事件只是新增 | `superseded_at` 软作废 + 取消接口 |
| 草稿跨账号串 | sessionStorage 用全局 key | 按 `user_id` 分区 + 退出清理 |
| 发现→Agent 丢筛选 | 多选企业被 `slice(0,5)` | 全量传递 + 提示词显式列出条件 |
| 推荐文字与卡片矛盾 | 汇总含 `excluded_count`，提示词未约束 | 只允许引用 `matches`，为空明说 |
| 测试库整体挂起 | 检查点 `CREATE INDEX CONCURRENTLY` 等测试事务 | `APP_ENV=test` 跳过初始化 |
| 岗位方向筛选失效 | 分类把算法/数据合并 | 拆 14 类 + 优先级排序 + 旧 key 组兼容 |
| 粘贴 JD 返回 500 | 私有导入强制走官方域名白名单 | 只校验 URL 形态，未知域名按用户填写建 Company |
| 简历项目没时间 | `ProjectItem` 无该字段 | 加 `time_range` + 解析映射 + 前端输入框 |
| 直连企业"点了必失败" | 未适配企业也出现在可点列表 | 目录标注 supported + 灰色按钮跳官网搜索 |

---

## 7. 面试常见追问与回答要点

1. **为什么用 LangGraph 而不是自己写循环？**
   需要可中断、可恢复、可取消、可观测；StateGraph 提供检查点与节点边界，正好是这四点的落点。

2. **Agent 怎么保证不胡说？**
   三道闸：工具白名单（只能查不能编）、输出结构约束（`matches` 之外不许推荐）、数据带来源与时间。

3. **SSE 与 WebSocket 怎么选？**
   场景是服务端单向推；SSE 走 HTTP、天然支持 `Last-Event-ID` 续传，无需心跳与连接管理。

4. **并发与一致性怎么处理？**
   run 抢占用行锁；事件单事务写入且 `sequence` 单调；同步任务 `for update` 防重叠；前端用代次令牌防旧响应覆盖。

5. **反爬与合规边界？**
   只读公开页、不登录、不绕验证码、不批量翻页、不自动投递；这条写进代码与产品约束。

6. **为什么不做定时自动同步？**
   基础设施已具备（beat + `content_hash` + `last_checked_at`），但需先解决"关键词覆盖"与"下架误杀"，否则会写入错误状态。

7. **最大的收获？**
   LLM 系统里约束要落在数据结构上；Agent 的可靠性来自状态机与证据链，不是提示词。

8. **规模数据？**
   89 接口 / 16 表 / 326 后端用例 / 40 前端用例 / 33 次提交 / 7 家官方直连 / 19 家企业目录 / 14 个岗位方向。

---

## 8. 继续加分的方向

- **可观测性**：run 的 token、耗时、工具调用次数落表，做成功率与 P95 面板；
- **评测集**：把 `M4_EVALUATION` 扩成回归集（问题 → 期望工具 → 期望结论），防提示词改动回归；
- **浏览器扩展**：用用户自身登录态读详情页，覆盖"需登录"站点（边界：只读当前页、不自动投递）；
- **结构化 JD**：把 JD 拆成职责/要求/技能条目，用于更细的匹配解释。

---

## 附：相关文档

- 架构：`docs/M2_R1_ARCHITECTURE.md`、`docs/M3_ARCHITECTURE.md`、`docs/M4_AGENT_ARCHITECTURE.md`、`docs/M5_FRONTEND_ARCHITECTURE.md`、`docs/M6_AGENT_ASYNC.md`
- 评估：`docs/M3_EVALUATION.md`、`docs/M4_EVALUATION.md`、`docs/M5_E2E_EVALUATION.md`
- 安全：`docs/M5_SECURITY_REVIEW.md`
- 使用：`docs/USER_GUIDE.md`
- 状态：`docs/IMPLEMENTATION_STATUS.md`
