# CareerPilot — 智能求职 Agent 系统核心开发规范（Codex 交付版）

> **版本**：v1.0 · 2026-10-21  
> **状态**：已确定的第一期开发基线（可按里程碑逐步实施）  
> **语言**：中文为主，界面和代码注释可中英混用；代码标识符统一使用英文  
> **产品定位**：国内互联网实习 / 校招岗位搜索、个人简历画像、岗位匹配与多 Agent 求职工作流。  
> **本期目标**：实现可部署、可测试、可追踪、真实数据与演示数据严格区分的 Web 应用。  
> **交付给 Codex 的性质**：本文件是需求、架构、开发规则、接口和验收规范的单一事实来源（Source of Truth）。

---

## 0. 给 Codex 的执行指令（务必先读）

你是本项目的实现工程师。请按本规范开发一个**可运行的全栈应用**，不要只输出设计或伪代码。**分里程碑实施，每个里程碑完成后运行测试、总结变更和遗留问题。**

1. 首先检查当前仓库；若为空，则初始化 Monorepo；若已有代码，则复用合理部分，不得擅自覆盖用户文件。
2. 严格按 **M0 → M1 → M2 → M3 → M4 → M5 → M6** 顺序实现；不得跳过测试直接堆砌页面。
3. 优先真实可用和可维护；外部数据源不可用时以 `unavailable` 呈现，**禁止将 mock 数据显示为真实岗位**。
4. 使用清晰、强类型的数据模型及可执行数据库迁移；不把所有业务写在一个 Agent Prompt 中。
5. 任何岗位的 `published_at`、薪资、截止日期、招聘状态，无法从来源核实时应存为 `null/unknown`，不可推断或编造。
6. **本期不自动向招聘网站提交申请，不绕过验证码/登录/反爬，不自动发邮件或外部消息**。仅提供官方申请链接和本系统内的手动投递记录。
7. 本期**不进行 SFT、DPO、RL、Reward 训练、学习排序等研究**；匹配优先采用可解释规则和可选的现成语义能力。
8. 所有 AI 输出与第三方网页文本均是不可信输入；所有数据库写操作由业务服务做验证与授权。
9. 外部 AI Key、第三方 API、公开招聘源可能缺失：**系统必须可在 `DEMO_MODE=true` 无外部凭据下完整启动并执行演示流程**。
10. 不要声称实现了尚未接入的平台。交付时列出已经连通的真实数据源、测试通过项及因凭据/平台规则而无法验证的项目。
11. 每项任务完成后更新 `docs/IMPLEMENTATION_STATUS.md`，包括完成项、测试命令及结果、下一项、风险。
12. 如发现规格冲突，优先遵循安全和数据真实性约束；以最小可行方案实现，并在状态文档中记录假设，不要长期停在询问阶段。

### 本期最终验收必须能演示两条完整链路

- **链路 A：岗位发现**：用户上传 PDF/DOCX 简历 → 确认/编辑个人技能与求职偏好 → 搜索岗位 → 展示来源/可核验时间 → 给出匹配分数与原因 → 收藏岗位。
- **链路 B：多 Agent 工作流**：用户输入“找最近 7 天北京/上海的 LLM/Agent 实习，按我的简历匹配并整理待投递清单” → Supervisor 解析意图 → JobSearch Agent 查询数据库/已授权连接器 → Profile Agent 提取/读取画像 → JobMatch Agent 匹配 → ApplicationPlanner Agent 生成待投递清单 → Agent 事件流可视化 → 重开网页后任务记录可查。

> “最近 7 天发布”只能使用来源可验证的 `published_at` 过滤。`published_at=null` 的岗位不得冒充最近发布岗位；可以单列为“发现时间较近，但发布时间未知”，并要求用户确认是否加入。

---

## 1. 产品范围与优先级

### 1.1 P0（本期必须完成）

| ID | 模块 | 需求 | 验收说明 |
|---|---|---|---|
| P0-01 | 身份与个人数据 | 用户注册/登录或安全的本地演示模式；不同用户数据隔离 | 跨用户请求返回 403/404，不泄漏岗位收藏、简历、记录 |
| P0-02 | 简历画像 | 上传 PDF/DOCX、提取文本、生成技能候选、编辑确认画像 | 原文件可查看/删除，抽取失败有提示，可手动编辑 |
| P0-03 | 求职偏好 | 岗位类型、城市、岗位关键词、意向公司、排除词 | 可保存并用于查询和 Agent 参数默认值 |
| P0-04 | 岗位数据 | 来源连接器、定时/手动同步、标准化、去重、状态核验 | 每个职位具备 `source_url` 与 `source_type` |
| P0-05 | 岗位搜索 | 关键词、公司、城市、岗位类型、来源、时间、分页、排序 | 刷新页面保留筛选条件；空结果友好提示 |
| P0-06 | 岗位详情 | 原文 JD、结构化字段、来源链接、首次发现/发布时间 | 时间来源清晰；字段缺失明确显示“未知” |
| P0-07 | 智能匹配 | 用户画像与岗位匹配、显示 0–100 启发式分和匹配/缺口理由 | 解释来自实际简历/岗位字段，不编造经历 |
| P0-08 | 收藏和清单 | 收藏、取消收藏、去重、建立待投递清单 | 同一用户同一岗位不会重复收藏 |
| P0-09 | 投递追踪 | 手工标记准备中/已投递/笔试/面试等，维护时间线 | 未得到证据时不能自动标记成功或淘汰 |
| P0-10 | Agent 编排 | Supervisor + 专业 Agent 参与有状态工作流 | 有结构化事件、运行状态、异常恢复、最大步数 |
| P0-11 | Agent Workspace | 对话任务输入、步骤展示、结果卡片、用户确认操作 | 能看到哪一步、使用了哪些来源、失败原因 |
| P0-12 | 工程化 | Docker Compose、本地启动、数据库迁移、种子数据、自动测试 | 新环境按 README 可复现 |

### 1.2 P1（下一期，**不是**本期验收阻塞项）

- InterviewResearch Agent：公开面经与面试流程的来源化检索。
- 简历针对 JD 的多个版本生成与 PDF 导出。
- 授权邮箱解析投递回执、日历提醒与招聘变更提醒。
- 更多中国大陆招聘平台的正式授权连接器；更复杂的跨来源职位合并。
- MCP Server：将稳定的搜索/画像/清单工具对外标准化暴露。
- Browser Automation：仅对明确允许的站点作辅助填写，并保留人工审批。

### 1.3 明确不做（Out of Scope）

全自动海投、验证码破解、账号凭据代管、直接查询无授权的企业 ATS 投递内部状态、抓取受限个人信息、模拟面试 Agent、模型训练/强化学习、多组织商业化计费、K8s 微服务拆分、完整 A2A 跨平台互联。

---

## 2. 用户与核心场景

### 2.1 目标用户

- 互联网大模型/Agent/NLP/推荐/后端等岗位求职者；优先覆盖实习和应届校招。
- 一人多份简历、多城市意向、多岗位关键词。
- 用户可以不上传简历，仅使用岗位搜索；此时不能给出个人化匹配分，提示先设置画像。

### 2.2 用户故事（必须具备）

**US-01：独立搜索**  
作为求职者，我想搜索“上海 Agent 算法实习”，看到来源可追溯的岗位、城市、发布时间、官方链接，并可按公司、岗位类型和时间过滤。

**US-02：简历匹配**  
作为求职者，我上传一份简历并修正识别出的技能，希望看到“为什么推荐 / 哪些技能符合 / 哪些岗位要求没有证据支持”。

**US-03：Agent 任务**  
作为求职者，我用一句话说明岗位需求，系统能够拆分搜索、画像、匹配、整理任务，并将结果展示为结构化卡片。

**US-04：投递清单**  
作为求职者，我想把岗位添加到待投递列表，打开官方投递链接，自己提交后记录状态和备注。

**US-05：断点恢复**  
作为求职者，刷新网页或重启后台后，我能够看到先前的 Agent 运行结果；未完成任务状态不应假装完成。

**US-06：数据透明**  
作为求职者，我需要区分 demo 岗位、正式同步岗位、仅手工添加的岗位；不愿看到系统推断的“今日发布”。

### 2.3 页面最小交互

- 不需要复杂的 ChatGPT 克隆 UI。
- 中文界面优先，桌面端优先，移动端可读。
- 常见空状态、错误、处理中状态都必须设计。

---

## 3. 选型决策与依赖边界

| 层级 | 本期选型 | 原则 |
|---|---|---|
| Web | Next.js（App Router）、React、TypeScript、Tailwind CSS、shadcn/ui | 前端独立模块化 |
| API | Python 3.11+、FastAPI、Pydantic v2 | OpenAPI 与类型校验 |
| ORM/Migration | SQLAlchemy 2.x + Alembic | Schema 可持续演进 |
| Agent | LangGraph StateGraph + LangChain 模型适配器 | 持久状态、显式流程控制 |
| LLM | OpenAI 兼容接口适配层（支持可配置 base_url/model/key） | 可连接国内/海外模型；无 Key 可降级 |
| Database | PostgreSQL + `pgvector` 扩展预留 | 事务数据为真相源，向量能力可选 |
| Queue | Redis + Celery Worker | 跑招聘源同步及 Agent 长任务，避免请求阻塞 |
| File | 本地开发目录，接口抽象为 FileStorage | 生产环境可接 S3/MinIO |
| API client | httpx（异步） | 连接器独立超时/限流/重试 |
| Document parser | PDF 文字提取工具 + python-docx | 扫描件无法可靠提取时提示手动处理 |
| Test | pytest、pytest-asyncio、httpx、Vitest、Playwright E2E | Mock-first，真实源测试可选 |
| Container | Docker Compose | `web`、`api`、`worker`、`postgres`、`redis` |
| Tracing | 标准结构化日志 + Agent runs/events；OpenTelemetry 可选 | 不依赖付费 SaaS 才可用 |

**检索约束**：首版使用标准化字段过滤、关键词归一化、`ILIKE/pg_trgm` 与可选向量召回；不要假装 PostgreSQL 普通全文搜索天然具备高质量中文 BM25。后续需要时引入中文分词和独立搜索引擎。

**LLM 降级约束**：无 `LLM_API_KEY` 时可运行确定性意图提取模板、用户画像的简单关键词提取、岗位匹配和预设多 Agent 工作流。不能宣称此时具有完整的自由自然语言理解能力；UI 须清楚标注“规则演示模式”。

**版本约束**：不硬编码猜测未来 patch 版本；在工程初始化时选择兼容且稳定的具体版本，生成 lockfile，README 记录实测版本。使用 LangGraph 当前官方 StateGraph/持久化 API，不使用已经弃用的旧教程接口。

---

## 4. 系统架构（模块化单体 + 异步工作进程）

```mermaid
flowchart TD
    U[用户浏览器] --> FE[Next.js Web]
    FE --> API[FastAPI API]
    API --> AUTH[身份和权限]
    API --> BIZ[业务服务 Jobs / Profiles / Applications]
    API --> RUN[Agent Run Service]
    API --> DB[(PostgreSQL)]
    RUN --> Q[(Redis Broker)]
    Q --> W[Celery Worker]
    W --> GRAPH[LangGraph Supervisor Workflow]
    GRAPH --> JS[Job Search Agent]
    GRAPH --> PA[Profile Agent]
    GRAPH --> JM[Job Match Agent]
    GRAPH --> AP[Application Planner Agent]
    JS --> BIZ
    PA --> BIZ
    JM --> BIZ
    AP --> BIZ
    W --> DB
    SCHED[定时/管理员触发同步] --> Q
    W --> CONNECT[受允许的数据连接器]
    CONNECT --> PUBLIC[公开岗位 API / 用户导入]
    API --> FILES[简历文件存储]
    FE -. SSE 事件 .-> API
```

### 4.1 模块职责

- **API**：认证、请求验证、DB 事务、查询接口、创建 Agent Run、SSE 事件订阅；不直接在 Web 请求中运行长时间 LLM 任务。
- **Worker**：岗位同步、Agent 任务、失败重试；写入结构化事件、执行结果和状态。
- **Domain Services**：负责数据读写、重复检测、状态转移和权限检查；Agent 不直接拼 SQL。
- **Agent Nodes**：负责理解意图、查询条件整理、选择工具、结果概括；不持有数据库管理权限。
- **Connectors**：只获取合法公开或经授权的数据；与 LLM 分离，便于离线测试。
- **DB**：是收藏、申请状态和岗位来源的真相源；LLM 上下文和运行日志不是业务真相源。

### 4.2 为什么不是全微服务

首期仅一个后端服务和一个异步 Worker，即可分开测试和扩展；不为展示“先进架构”而额外引入消息总线、K8s、A2A 或多个 Agent 独立部署服务。

---

## 5. 招聘数据接入与真实数据保障

### 5.1 首版数据源类型

1. `fixture`：离线演示文件，包含明显的 `is_demo=true` 标记，仅 Demo 模式启用。
2. `manual`：用户手动添加招聘链接或管理员导入经许可的岗位文件；保存原始出处，不自动判定发布时间。
3. `greenhouse_public`：按已验证的企业 `board_token` 调用公开岗位 GET 接口。
4. `lever_public`：按已验证的公司 `site` 调用公开 Postings GET 接口。
5. `ashby_public`：按已验证的企业 `job_board_name` 调用公开 Job Postings API。
6. `approved_company_site`：预留适配器；只有经过人工确认访问许可、稳定性和字段准确性后才能启用。

> Greenhouse / Lever / Ashby 是可运行的公共数据源样例，并**不代表中国头部互联网公司必然使用这些系统**。中国企业来源接入采取“源清单登记 → 人工验证 → 单站连接器”的方式；不承诺未接入的网站已覆盖。

### 5.2 Connector 协议

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Literal

@dataclass
class RawJob:
    source_type: str
    source_key: str           # 唯一来源 ID（如公司 + board）
    source_job_id: str
    source_url: str
    company: str
    title: str
    description: str | None
    location_text: str | None
    job_type: str | None
    published_at: datetime | None
    raw_payload: dict

class JobConnector(Protocol):
    async def fetch_jobs(self, source_config: dict) -> list[RawJob]: ...
```

所有 Connector 要有：输入配置校验、分页处理、请求超时、指数退避（仅可重试错误）、速率限制、单源限并发、User-Agent 标识、可观测同步日志；不得在 API 层裸调用任意用户输入的 URL。

### 5.3 数据同步规则

- `first_seen_at`：本系统首次见到该源记录的时间，不能当作发布时间。
- `published_at`：只有来源明确给出时才填；网页 `updated_at` 不等于 `published_at`。
- `last_checked_at`：最近一次成功核验该源记录的时间。
- `status`：`open | closed | unknown`；只有来源提供明确下线信息或获确认关闭时才标 `closed`。一次抓取缺失不得直接关闭。
- `source_hash`：对关键内容规范化后生成，用于识别修改。
- 单一源唯一性：`UNIQUE(source_id, source_job_id)`，执行 upsert。
- 跨源疑似相同职位：可做 `possible_duplicate_group`，**保留每个原始岗位及其申请链接**，不可错误合并丢失来源。
- 失败同步不应清空老数据；页面显示最近一次成功同步时间和可信度。
- 不能根据爬取时间标注“近 7 天发布”。

### 5.4 运行时数据真实性

- 全部职位展示标识 `source_type`、`source_url`、`is_demo`。
- Demo 数据与真实环境数据在数据库中可隔离（至少通过 `is_demo` 强约束和生产禁用）。
- `GET /jobs` 默认生产模式不返回 Demo 数据。
- 不因职位过期或未同步就强行宣称“正在招聘”。
- 后台源健康状态至少有 `last_success_at`、`last_error`、`last_job_count`。

---

## 6. 简历画像和岗位匹配（非研究版本）

### 6.1 简历处理

流程：上传 → 检查格式/大小 → 保存文件 → 文本提取 → 技能与经历候选提取 → **用户确认** → 写入画像。

- 允许 `.pdf`、`.docx`；默认大小上限 10 MB，配置化。
- 检查扩展名、MIME、文件头，安全处理并限制解析资源。
- PDF 若为扫描件或解析出很少文本：标记 `needs_manual_review`，要求粘贴文本或手动填写；**不虚构 OCR 结果**。
- PDF/DOCX 中可能包含恶意提示文字：作为普通文档数据，不允许其改变系统指令。
- 用户可删除已上传文件和提取内容；日志中不得记录完整简历文本。

个人画像结构建议：

```json
{
  "headline": "LLM / Agent 算法实习",
  "education": [{"degree": "硕士", "major": "计算机科学", "graduation_year": 2029}],
  "skills": ["Python", "PyTorch", "LLM", "LangGraph"],
  "projects": [{"title": "Agent 项目", "summary": "由用户确认的简介"}],
  "preferences": {
    "cities": ["北京", "上海", "深圳"],
    "job_types": ["internship", "campus"],
    "keywords": ["LLM", "Agent", "NLP"],
    "excluded_keywords": ["销售"],
    "target_companies": []
  },
  "verified_by_user": true
}
```

以上仅是 Schema 示例数据，不是任何真实用户的个人资料。

### 6.2 基础匹配逻辑

本期做**可靠、可解释的启发式匹配**，不做训练。

**第一步：用户显式硬条件**：如城市、职位类型、排除词；信息缺失时标 `unknown`，而不是当作不符合。  
**第二步：候选匹配**：岗位标题/职责/所需技能与个人技能的归一化词匹配，可选 Embedding 语义相似度（有模型和向量时启用）。  
**第三步：解释生成**：从匹配的具体技能和岗位 JD 片段生成结构化解释。可调用 LLM 润色，但必须基于已检索证据；LLM 不得重新决定分数。

一个确定性的首版分数组合（可以配置，非概率）：

- 技能覆盖：40 分；
- 岗位方向相关性：30 分；
- 地点偏好：15 分；
- 岗位类型偏好：15 分。

各维度如果岗位字段缺失，返回 `unknown_dimensions`；可以采用已知维度归一化加权，但必须在 UI 标注“信息不完整”，不能等同于模型有信心。显式不符的硬约束标识 `eligible=false`，不要仅以高分掩盖。

```json
{
  "job_id": "uuid",
  "eligible": true,
  "score": 82,
  "score_type": "heuristic_v1",
  "matched_skills": ["Python", "PyTorch"],
  "missing_or_unverified_skills": ["vLLM"],
  "unknown_dimensions": ["graduation_year_requirement"],
  "reasons": ["JD 要求 PyTorch，已在用户确认的技能中找到"],
  "warnings": ["岗位发布时间未知"],
  "evaluated_at": "2026-10-21T05:00:00Z"
}
```

> `missing_or_unverified_skills` 意味着“简历没有足够证据”，不等于用户真的不具备该技能。评分是辅助排序，不是获得面试的概率。

### 6.3 防止不必要的重复计算

- 优先做按需匹配；列表分页每次最多匹配 20～50 个职位。
- 根据 `profile_version + job_content_hash + scorer_version` 缓存结果。
- 用户更新画像、JD 更新或评分策略改变时失效。

---

## 7. 多 Agent 工作流（核心实现）

### 7.1 首期 Agent 划分

| Agent / Node | 职责 | 允许工具 | 明确禁止 |
|---|---|---|---|
| `Supervisor` | 解析自然语言、选择意图和流程、补全可确认的缺省参数 | `parse_intent`, `route_workflow` | 对外提交申请、直接修改数据库 |
| `JobSearchAgent` | 整理搜索条件，调用职位搜索服务，返回职位 ID 与来源 | `search_jobs`, `get_job_details`, `get_source_health` | 无许可联网抓取、捏造岗位 |
| `ProfileAgent` | 读取已确认简历画像、指出缺失字段 | `get_profile`, `get_resume_summary` | 静默修改用户画像 |
| `JobMatchAgent` | 对职位执行可解释评分和排序 | `rank_jobs`, `get_match_explanations` | 仅凭 LLM 主观打分 |
| `ApplicationPlannerAgent` | 对未投递岗位生成待投递候选和操作建议 | `check_application_history`, `draft_apply_list` | 直接在外部平台投递 |
| `ResultVerifier`（确定性节点） | 验证职位 ID、时间过滤、链接、重复、结果数 | Domain Services | 依赖 LLM 判断数据库存在性 |

> Multi-Agent 在本期表现为有独立职责、工具边界和节点输入输出的专业子 Agent；不强制每个节点都调用一次大模型。确定性节点可以共享一个工作流，不必为“多智能体”增加虚假的独立人格。

### 7.2 核心状态图

```mermaid
flowchart TD
  START([START]) --> SUP[Supervisor: 解析意图]
  SUP --> VALID[校验参数和预算]
  VALID --> ROUTE{业务意图}
  ROUTE -->|岗位搜索| SEARCH[JobSearchAgent]
  ROUTE -->|搜索+匹配/清单| FORK[并行获取]
  ROUTE -->|我的收藏| SAVED[读取 SavedJobs Service]
  ROUTE -->|投递进度| TRACK[读取 Applications Service]
  FORK --> SEARCH2[JobSearchAgent]
  FORK --> PROFILE[ProfileAgent]
  SEARCH2 --> JOIN[合并候选与画像]
  PROFILE --> JOIN
  JOIN --> MATCH[JobMatchAgent]
  MATCH --> PLAN[ApplicationPlannerAgent]
  SEARCH --> VERIFY[ResultVerifier]
  PLAN --> VERIFY
  SAVED --> VERIFY
  TRACK --> VERIFY
  VERIFY --> RESP[构建结构化结果]
  RESP --> END([END])
  VALID -->|关键参数缺失| ASK[返回 clarification_needed]
  ASK --> END
  VERIFY -->|可恢复错误且未超预算| RETRY[有限重试]
  RETRY --> SEARCH2
```

**不实现无边界自由循环**：每次 Run 最多 8 次工具调用（配置化），外部 API 超时 10–20 秒，Run 总执行预算 90 秒（配置化），重试最多 2 次，仅针对幂等读取操作。

### 7.3 意图与澄清

首期支持：`search_jobs`、`match_jobs`、`build_apply_plan`、`show_saved_jobs`、`show_application_status`；不支持时返回能力边界说明。

Supervisor 输出 Pydantic 结构化对象：

```json
{
  "intent": "build_apply_plan",
  "filters": {
    "keywords": ["LLM", "Agent"],
    "cities": ["北京", "上海"],
    "job_types": ["internship"],
    "published_after": null,
    "published_within_days": 7,
    "require_verified_publish_date": true
  },
  "use_profile": true,
  "exclude_already_applied": true,
  "limit": 20,
  "needs_clarification": false
}
```

- 用户未指定城市/类型时从用户偏好读取；无偏好则不施加强过滤。
- “最近 N 天发布”：按系统 UTC 时间换算日期范围，必须有可验证 `published_at`。
- 若要求“匹配我的简历”但尚无已确认画像，工作流返回 `needs_profile` 和引导操作；不得伪造匹配。
- 若用户请求执行对外投递，返回 `unsupported_external_action`，仅生成手动操作清单。

### 7.4 AgentState（示意，必须落实为强类型）

```python
from typing import TypedDict, Literal

class AgentState(TypedDict, total=False):
    run_id: str
    thread_id: str
    user_id: str
    user_message: str
    intent: str
    filters: dict
    user_profile: dict | None
    candidate_job_ids: list[str]
    matched_jobs: list[dict]
    apply_plan: list[dict]
    sources_used: list[dict]
    warnings: list[str]
    pending_action: dict | None
    error_code: str | None
    status: Literal[
        "queued", "running", "needs_profile", "clarification_needed",
        "waiting_approval", "completed", "failed", "cancelled"
    ]
    step_count: int
```

**数据边界**：State 中尽量存 job_id/摘要，不存完整 PDF、邮箱凭据、任意长的 JD；完整数据按授权从业务服务读取。State 里的 `user_id` 来自身份验证上下文，绝不能由 LLM 输出决定。

### 7.5 Checkpointer、运行恢复和事件

- 生产使用 PostgreSQL Checkpointer；开发允许内存版，但集成测试必须覆盖持久化版。
- `thread_id`：一次可持续的会话线程；`run_id`：用户的一次请求执行。二者不得混淆。
- 将 `agent_runs` 与 `agent_run_events` 写 DB，用于产品查询与审计；Checkpoint 用于 LangGraph 内部恢复。
- SSE 只负责**增量展示**，断线后按 `run_id + after_event_id` 补读数据库事件。
- 并发写同一 `thread_id` 应串行化或返回 409，避免交叉污染状态。
- 若 Run 中断，前端展示 `waiting_approval / clarification_needed` 等真实状态，不将其误报为成功。
- 中断恢复时避免在重复执行的节点中先执行副作用；业务写入必须有幂等键。
- AI 服务不可用且无法按规则模式处理任务时，Run 状态为 `failed`；若成功执行规则回退则仍可 `completed`，但结果中必须有 `execution_mode=rule_fallback` 和清晰的降级警告，不能显示“已成功智能分析”。

### 7.6 Agent 事件流契约

事件类型：

`run_created`, `run_started`, `agent_started`, `tool_started`, `tool_completed`, `agent_completed`, `result_ready`, `clarification_required`, `approval_required`, `run_completed`, `run_failed`。

示例：

```json
{
  "id": 208,
  "run_id": "uuid",
  "event_type": "tool_completed",
  "agent": "JobSearchAgent",
  "payload": {
    "tool_name": "search_jobs",
    "count": 12,
    "source_types": ["greenhouse_public", "manual"],
    "duration_ms": 430
  },
  "created_at": "2026-10-21T05:00:00Z"
}
```

事件必须脱敏：禁止输出 API Token、完整 Cookie、文件二进制或简历原文。需为事件表设置保留期和清理策略。

### 7.7 用户写操作与确认

首期的收藏、清单创建、投递状态修改，由用户直接在 UI 中触发写接口。Agent 只能生成 `draft_apply_list` 候选，若用户在聊天中要求“一键加入清单”，则必须返回待确认提案并在用户点击确认后写入；写入由后端验证权限与幂等键。后续外部投递必须新增单独审批断点，**不可复用收藏确认当作投递授权**。

---

## 8. 数据库设计（PostgreSQL）

使用 UUID 主键、`created_at`/`updated_at`（UTC timestamptz）、必要的唯一约束、Alembic migration。敏感 JSON 字段需严格控制读取范围。

| 表 | 关键字段 | 约束 / 说明 |
|---|---|---|
| `users` | `id`, `email`, `password_hash`, `created_at` | 邮箱唯一；若用第三方登录，改为 provider id |
| `candidate_profiles` | `id`, `user_id`, `headline`, `skills_json`, `education_json`, `projects_json`, `version`, `verified_by_user` | `UNIQUE(user_id)`；画像编辑升级版本 |
| `job_preferences` | `user_id`, `cities_json`, `job_types_json`, `keywords_json`, `excluded_keywords_json`, `target_companies_json` | 一用户一份 |
| `resumes` | `id`, `user_id`, `original_name`, `content_type`, `storage_key`, `parse_status`, `extracted_text`, `is_primary` | 限制文件访问；支持删除 |
| `companies` | `id`, `name`, `normalized_name`, `website` | 归一化名称索引 |
| `job_sources` | `id`, `source_type`, `source_key`, `config_json`, `enabled`, `last_success_at`, `last_error`, `last_job_count` | `UNIQUE(source_type, source_key)`；源配置校验 |
| `jobs` | `id`, `source_id`, `source_job_id`, `company_id`, `title`, `location_text`, `job_type`, `description`, `requirements_json`, `source_url`, `published_at`, `first_seen_at`, `last_checked_at`, `status`, `content_hash`, `is_demo` | `UNIQUE(source_id, source_job_id)`；支持软删除/状态变更 |
| `saved_jobs` | `id`, `user_id`, `job_id`, `list_type`, `note` | `UNIQUE(user_id, job_id, list_type)`；`list_type=saved/to_apply` |
| `applications` | `id`, `user_id`, `job_id`, `resume_id`, `status`, `applied_at`, `source_of_truth`, `notes` | `UNIQUE(user_id, job_id)`；本期为用户手动记录 |
| `application_events` | `id`, `application_id`, `from_status`, `to_status`, `actor`, `evidence_type`, `note`, `created_at` | 只追加的状态历史 |
| `agent_threads` | `id`, `user_id`, `title`, `created_at` | `thread_id` 与 user 绑定 |
| `agent_runs` | `id`, `thread_id`, `user_id`, `intent`, `status`, `input_json`, `result_json`, `error_code`, `started_at`, `finished_at` | `run_id` 唯一；需要状态索引 |
| `agent_run_events` | `id` (bigserial), `run_id`, `event_type`, `agent`, `payload_json`, `created_at` | `(run_id,id)` 索引，支持断线补偿 |
| `action_proposals` | `id`, `run_id`, `user_id`, `action_type`, `payload_json`, `status`, `expires_at`, `idempotency_key` | `UNIQUE(user_id,idempotency_key)`；审批专用 |
| `sync_runs` | `id`, `source_id`, `status`, `fetched_count`, `upserted_count`, `error_message`, `started_at`, `ended_at` | 数据源同步审计 |

### 8.1 状态枚举

- `JobStatus`: `open`, `closed`, `unknown`
- `ResumeParseStatus`: `pending`, `parsed`, `needs_manual_review`, `failed`
- `ApplicationStatus`: `to_apply`, `preparing`, `applied`, `online_assessment`, `interview`, `offer`, `rejected`, `withdrawn`, `closed`, `unknown`
- `AgentRunStatus`: `queued`, `running`, `needs_profile`, `clarification_needed`, `waiting_approval`, `completed`, `failed`, `cancelled`
- `ActionProposalStatus`: `pending`, `approved`, `rejected`, `expired`, `executed`, `failed`

### 8.2 关键完整性规则

1. `user_id` 只从认证中间件注入，所有用户专属表查询必须附加用户过滤。
2. 应聘申请必须指向现有岗位；若同用户对同岗位重复添加，应返回现有记录或 409，不生成重复行。
3. 每次用户修改申请状态写 `application_events`，与主表事务一致。
4. 用户删除简历时，清理文件存储，并根据关系约束保留合法历史记录或解除简历关联。
5. `source_url` 只允许 http/https；后台网络请求必须使用白名单、禁止内网地址及重定向绕过（防 SSRF）。
6. `is_demo` 默认 false，只有演示数据导入器可以设置 true。
7. 数据库 schema 要创建必要索引：职位 `(source_id,source_job_id)`、`company_id`、`job_type`、`published_at`、`first_seen_at`、`status`；用户记录 `(user_id,created_at)`；搜索文本 trigram 索引可在 migration 启用。

---

## 9. 后端 API 契约（统一 `/api/v1`）

### 9.1 通用规范

- Content-Type JSON，简历上传使用 multipart/form-data。
- 所有 API 按认证用户授权；返回分页 `page`, `page_size`, `total`。
- 错误格式统一：`{"error":{"code":"...","message":"...","details":{}}}`。
- HTTP：401 未登录、403 无权限、404 资源不存在、409 冲突、422 参数错误、429 限流、503 依赖不可用。
- 开启 OpenAPI `/docs`（生产环境可限制）。
- 约定所有时间用 ISO 8601 UTC `...Z`，UI 按用户时区格式化。

### 9.2 主要接口清单

| Method | Path | 功能 |
|---|---|---|
| GET | `/healthz` | 进程存活，不需要 DB 依赖 |
| GET | `/readyz` | DB/Redis 等关键依赖就绪 |
| POST | `/api/v1/auth/register` | 注册（生产） |
| POST | `/api/v1/auth/login` | 登录（会话或安全 HttpOnly Cookie） |
| POST | `/api/v1/auth/logout` | 退出 |
| GET/PATCH | `/api/v1/profile/me` | 读取/更新个人画像和偏好 |
| POST | `/api/v1/resumes` | 上传并创建解析任务 |
| GET | `/api/v1/resumes` | 我的简历列表 |
| GET | `/api/v1/resumes/{id}` | 简历元信息和解析状态 |
| DELETE | `/api/v1/resumes/{id}` | 删除简历 |
| GET | `/api/v1/jobs` | 岗位查询和分页 |
| GET | `/api/v1/jobs/{id}` | 岗位详情 |
| POST | `/api/v1/jobs/{id}/save` | 收藏或加待投递列表，幂等 |
| DELETE | `/api/v1/jobs/{id}/save` | 取消收藏（支持 `list_type`） |
| GET | `/api/v1/saved-jobs` | 收藏和待投递清单 |
| POST | `/api/v1/matches` | 批量匹配当前用户画像和职位 |
| POST | `/api/v1/applications` | 创建本系统内投递记录 |
| GET | `/api/v1/applications` | 投递看板，状态过滤 |
| GET | `/api/v1/applications/{id}/events` | 投递状态时间线 |
| PATCH | `/api/v1/applications/{id}/status` | 用户手动修改投递状态 |
| POST | `/api/v1/agent/threads` | 创建 Agent 会话 |
| GET | `/api/v1/agent/threads` | 我的 Agent 会话列表 |
| POST | `/api/v1/agent/threads/{id}/messages` | 发送自然语言任务，返回 run ID |
| GET | `/api/v1/agent/runs/{id}` | 查询执行状态和最终结果 |
| GET | `/api/v1/agent/runs/{id}/events` | SSE 事件流；支持 `after_event_id` |
| GET | `/api/v1/agent/threads/{id}/history` | 历史消息与结果 |
| POST | `/api/v1/agent/proposals/{id}/decision` | 对清单写入提案进行确认/拒绝 |
| GET | `/api/v1/sources` | 数据源健康与可用状态 |
| POST | `/api/v1/admin/sources/{id}/sync` | 管理员手工触发同步 |

### 9.3 岗位查询示例

```http
GET /api/v1/jobs?q=Agent&cities=上海,北京&job_types=internship&sort=published_at_desc&page=1&page_size=20
```

```json
{
  "data": [
    {
      "id": "uuid",
      "company": "Example Company",
      "title": "Agent Algorithm Intern",
      "city": "上海",
      "job_type": "internship",
      "source_type": "fixture",
      "source_url": "https://example.org/careers/123",
      "published_at": null,
      "first_seen_at": "2026-10-21T04:00:00Z",
      "status": "unknown",
      "is_demo": true
    }
  ],
  "meta": {"page": 1, "page_size": 20, "total": 1}
}
```

**示例仅为接口结构样本**，不能作为真实职位导入生产。真实 `source_url` 由正式数据源生成，不能以 `example.org` 展示“可申请”。

`GET /jobs` 必须提供：`q`, `companies`, `cities`, `job_types`, `source_types`, `published_after`, `published_before`, `published_date_known`, `status`, `sort`, `page`, `page_size`；默认最大 `page_size=50`，拒绝不合法组合。

### 9.4 匹配接口

```http
POST /api/v1/matches
Content-Type: application/json

{"job_ids":["uuid-1","uuid-2"],"profile_version":3}
```

响应：`data` 为第 6.2 节的数组；画像不存在或未经确认返回 409 `PROFILE_NOT_READY`；每次最多 50 个岗位，所有岗位 ID 必须合法。

### 9.5 Agent 运行接口

```http
POST /api/v1/agent/threads/{thread_id}/messages
Content-Type: application/json

{"message":"找最近7天北京上海的LLM实习，结合简历整理待投递岗位"}
```

响应：`202 Accepted`：

```json
{
  "data": {
    "thread_id": "uuid",
    "run_id": "uuid",
    "status": "queued",
    "events_url": "/api/v1/agent/runs/uuid/events"
  }
}
```

SSE：

```text
id: 208
event: tool_completed
data: {"id":208,"run_id":"uuid","agent":"JobSearchAgent","payload":{"count":12}}

```

SSE 必须支持 `Last-Event-ID` 或 `after_event_id` 补读并心跳；终态事件后关闭或继续允许历史重放，具体策略要在前后端一致。

### 9.6 用户状态修改示例

```http
PATCH /api/v1/applications/{id}/status
Content-Type: application/json

{"status":"interview","note":"用户手动记录：收到面试邀请"}
```

业务服务先验证用户拥有记录、状态枚举合法、请求没有重复提交。系统不能因为用户打开了官方链接就自动写成 `applied`。

---

## 10. 前端页面与信息架构

### 10.1 页面路由

| 路由 | 核心组件 |
|---|---|
| `/login` | 登录/注册 |
| `/dashboard` | 近期岗位、收藏/待投递统计、近期 Agent 执行 |
| `/jobs` | 搜索栏、筛选器、岗位列表、排序、分页 |
| `/jobs/[id]` | JD 详情、来源、匹配解释、收藏、跳转官方页面 |
| `/profile` | 简历上传、解析状态、画像编辑、偏好配置 |
| `/workspace` | Agent 聊天与结构化执行事件、任务结果 |
| `/applications` | 待投递清单 + 手动状态看板与时间线 |
| `/settings` | 账户、数据删除、数据来源透明说明 |

### 10.2 交互规则

- 样式：现代、简洁、专业，响应式，但优先 1440px 桌面体验。
- 左侧导航 + 主内容区；Agent Workspace 可用右侧详情抽屉。
- 岗位卡片必展示：公司、名称、城市、招聘类型、数据来源、发布日期（若无则“未知”）、可查看原网页。
- 匹配卡片展示评分口径 `heuristic_v1` 和解释，不显示“录取概率 82%”一类误导性文案。
- API 错误、无数据、LLM 未配置、连接器不可用、加载中、同步时间未知必须有可见状态。
- Demo 模式应用顶部有持续可见的 `演示数据 / 部分功能为规则模式` 标识。
- 搜索条件同步 URL Query，以支持刷新/复制链接。
- 多 Agent 页面用步骤时间线和结构化 JobCards 展示结果，不渲染隐藏的内部思考内容。
- 用户发起写入操作前清楚展示影响范围，并进行确认；成功/失败状态基于后端响应。
- 允许取消未开始的排队任务；运行中的任务使用软取消标记，在安全节点检查。

---

## 11. 目录规划（建议，不要求每个目录第一天创建）

```text
career-pilot/
├── apps/
│   └── web/
│       ├── app/                       # Next.js App Router
│       ├── components/                # UI + business components
│       ├── lib/                       # Typed API client, utilities
│       ├── hooks/                     # SSE / queries / local state
│       └── tests/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/v1/                  # auth, jobs, profile, matches, agent...
│   │   ├── auth/                    # password/session/auth dependencies
│   │   ├── core/                    # settings, logging, errors
│   │   ├── db/                      # session, models, migrations
│   │   ├── schemas/                 # Pydantic contracts
│   │   ├── services/                # domain logic, permission checks
│   │   ├── repositories/            # ORM data access
│   │   ├── connectors/              # fixture, manual, greenhouse, lever, ashby
│   │   ├── resume/                  # extraction and profile proposals
│   │   ├── matching/                # heuristic scorer
│   │   ├── agents/
│   │   │   ├── graph.py
│   │   │   ├── state.py
│   │   │   ├── supervisor.py
│   │   │   ├── job_search.py
│   │   │   ├── profile.py
│   │   │   ├── job_match.py
│   │   │   ├── application_planner.py
│   │   │   ├── verifier.py
│   │   │   └── tools.py
│   │   ├── workers/                 # Celery tasks and scheduling
│   │   └── storage/                 # abstract FileStorage
│   ├── alembic/
│   └── tests/                      # unit, integration, fixtures
├── evals/                           # 固定的功能回归任务（非算法训练）
├── fixtures/                        # 显式 Demo 岗位数据
├── infra/                           # Docker Compose / Dockerfiles
├── docs/
│   ├── IMPLEMENTATION_STATUS.md
│   ├── API.md
│   ├── DATA_SOURCES.md
│   └── DECISIONS.md
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

---

## 12. 环境变量与运行模式

必须提供 `.env.example`，不包含真实密钥：

```dotenv
APP_ENV=development
DEMO_MODE=true
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_PORT=3000
FRONTEND_BASE_URL=http://localhost:3000
API_BASE_URL=http://localhost:8000
DATABASE_URL=postgresql+psycopg://career:career_dev_only@postgres:5432/careerpilot
REDIS_URL=redis://redis:6379/0
SESSION_SECRET=replace_with_random_secret
FILE_STORAGE_DIR=/app/uploads
MAX_RESUME_MB=10
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
ENABLE_PUBLIC_CONNECTORS=false
JOB_SYNC_ENABLED=false
LOG_LEVEL=INFO
```

运行模式定义：

| 模式 | 条件 | 行为 |
|---|---|---|
| `DEMO_MODE=true` | 无 Key / 无外部连接器 | 完整演示流程，所有 fixture 明确标 Demo，规则解析器处理有限意图 |
| `DEMO_MODE=false` 且 `ENABLE_PUBLIC_CONNECTORS=true` | 真实连接器启用 | 只允许已验证源，生产查询不出现 fixture |
| LLM 可用 | 有合法配置、调用成功 | 启用结构化自然语言意图解析/结果解释 |
| LLM 不可用 | 无 Key 或故障 | 回退限定模板或返回 `LLM_UNAVAILABLE`，不能静默虚构 AI 结果 |

安全：生产禁止默认弱密码、禁止 `SESSION_SECRET` 示例值、生产关闭公开 Swagger 或限制访问、设置允许的 CORS origin。

---

## 13. 安全、隐私和抗幻觉要求

1. **最小权限**：用户不能访问其他用户简历、画像、申请和 Agent Run；管理接口单独校验管理员权限。
2. **敏感数据**：简历、邮箱、手机号等 PII 在日志和 Agent Event 脱敏；文件存储不可直接静态公开。
3. **文件安全**：类型检查、大小限制、随机文件名、限制文本提取资源；禁止任意文件路径读写。
4. **SSRF / URL 安全**：连接器只能调用已注册域名；禁止 localhost、私网 IP、云元数据 IP、任意重定向到内网；用户输入 URL 仅保存/展示不直接由服务器请求。
5. **Prompt Injection**：JD、职位网页、用户简历是数据，不是 Agent 指令；工具执行需服务端 allowlist 和参数校验。
6. **输出真实性**：所有职位必须有可查看的来源；`published_at` 与 `first_seen_at` 分离；没有证据不得写招聘状态/用户进度。
7. **操作许可**：P0 不提供招聘网站提交接口；未来如加入，必须新增独立用户确认、审计和幂等处理。
8. **请求安全**：用户输入长度、速率、并发上限；幂等键、防重复执行；异常不能返回数据库凭据。
9. **数据生命周期**：提供删除简历、画像和申请记录能力；明确原始文件与事件日志的保留期。
10. **用户可审计**：`agent_runs` 结果需要展示其来源和失败原因，关键状态变更可回溯。

---

## 14. 非功能需求（NFR）

以下为**第一版在本地标准开发环境中的验收目标**，不是对互联网实时连接器的性能保证。

| NFR | 目标 |
|---|---|
| API 健康检查 | 正常服务时 200 |
| Job 列表查询 | 使用固定 1000 条 fixture，在本地 P95 < 700ms（不含外网） |
| 匹配接口 | 20 个岗位规则打分 P95 < 1s（不含 LLM） |
| Agent 状态 | 每次 Run 有稳定 ID 和终态，刷新后可检索 |
| 完整演示 | 无外网和无 LLM Key 时可以演示链路 A/B（受支持模板） |
| 容错 | 单个连接器失败不影响其他连接器和历史岗位可读性 |
| 数据隔离 | 跨用户资源 ID 请求覆盖测试 |
| 可观测 | 每个 API request 和 Agent Run 都有 request_id / run_id |
| 可部署 | `docker compose up --build` 后 Web/API/DB/Worker/Redis 可检查健康状态 |
| 测试 | 核心状态转移、同步去重、岗位过滤、简历解析、Agent 路由、鉴权均有自动化测试 |

---

## 15. 必须实现的测试用例

### 15.1 纯业务单元测试

- 同一来源相同 `source_job_id` 连续同步两次不会新增重复岗位。
- 不同来源的类似岗位不会误覆盖原始来源链接。
- `published_at=null` 的职位不在“最近 7 天发布”结果中。
- 画像缺失时不可产生个人匹配分。
- 已投递的岗位在 `exclude_already_applied=true` 时被正确排除。
- 手动标记 `interview` 创建唯一事件，并按事务更新申请主表。
- 对同一岗位重复收藏不插入两条相同记录。

### 15.2 Agent 集成测试（固定 Tool Mock）

- “找上海 Agent 实习”能路由到搜索，并返回规范职位 IDs。
- “结合简历匹配”会读取画像并调用 Matching Service；若无画像返回 `needs_profile`。
- “最近 7 天”严格依据 `published_at` 而不是 `first_seen_at`。
- `build_apply_plan` 仅生成草稿，不会创建外部提交行为。
- Agent 工具失败可出现明确的 `run_failed` 或可恢复错误；有限重试不会无限循环。
- 同一 `thread_id` 并发新请求受到串行化或返回 409。
- 断开 SSE 重连可通过 `after_event_id` 补齐事件。
- 重新创建 Worker 后，已完成的 Run 依然可在 DB 查询；Checkpoint 持久化工作正常。

### 15.3 前端 E2E

- 登录 → 上传合法简历 → 修改画像 → 搜索岗位 → 查看详情 → 匹配 → 收藏。
- 发送 Agent 消息 → 展示步骤 → 返回岗位卡片 → 加入待投递清单。
- 刷新页面 → 会话仍在；Run 状态与结果一致。
- Demo 模式横幅始终显示；岗位无法访问时不出现虚假“立即投递成功”。

### 15.4 测试数据

- 固定包含：合法公开职位样例（网络响应 Mock）、无发布日期、已关闭、同源重复、跨源同名、无城市、中文技能同义词、空 JD、含恶意提示语的 JD、用户 A/B 隔离样本。
- 真实连接器测试使用**明确 opt-in 的网络测试**，允许失败/跳过但报告结果；CI 默认不依赖外部网站可用性。

---

## 16. 开发里程碑与 DoD（Codex 按顺序执行）

### M0 — 项目初始化和启动（优先级最高）

**任务**：初始化仓库；前后端最小应用；Docker Compose；Postgres/Redis；环境变量模板；格式化/Lint/Test 框架；README；统一错误和日志结构。

**DoD**：
- `docker compose up --build` 可启动全部基础服务；
- Web 能打开 `/dashboard` 初始页，API `/healthz`、`/readyz` 正常；
- `make lint`、`make test` 可执行，即使测试数量少；
- 不需要 LLM Key 或招聘平台凭据即可启动；
- 写入 `docs/IMPLEMENTATION_STATUS.md`。

### M1 — DB / 认证 / 核心业务模型

**任务**：SQLAlchemy 模型和 Alembic；账号认证与用户隔离；岗位、画像、收藏、投递状态 CRUD；fixture seed。

**DoD**：
- 迁移和 seed 可重复执行；
- User A/B 数据隔离测试通过；
- `GET /jobs` 查询/过滤/分页与收藏 CRUD 可用；
- 手工投递状态和事件按事务保存；
- Demo 职位全部显示 `is_demo=true`。

### M2 — 真实招聘数据连接器和同步

**任务**：Connector 基类、fixture/manual、至少一个公开 ATS 真正可用的连接器，另两个接口实现及 Mock 测试；标准化、同步日志、去重与源健康展示。

**DoD**：
- fixture 数据不冒充真实岗位；
- 能通过管理员操作触发一次受允许源的同步；
- 没有真实可用的 board/site 配置时如实显示“未配置”；
- 非法域名、不安全 URL 和限流/超时都有测试；
- 近 7 天过滤不会误用发现时间。

### M3 — 简历上传、画像和可解释匹配

**任务**：文件上传/删除、文本解析、用户编辑确认；规则评分服务和批量匹配 API；职位详情的匹配结果 UI。

**DoD**：
- PDF/DOCX 文字简历可解析；失败时可手动填写；
- 未确认画像不允许显示个人分；
- 每个匹配结果含分数口径、对应证据与字段缺失说明；
- 20 职位本地规则匹配性能目标达标。

### M4 — LangGraph Supervisor + 多 Agent 主流程

**任务**：状态 Schema、Graph 节点、Tool Service Adapter、Celery 运行、Postgres Checkpointer、Run/Event 存储、超时、重试、结构化输出；LLM 可用/不可用两种路径。

**DoD**：
- 路由覆盖 `search_jobs`、`match_jobs`、`build_apply_plan`、`show_saved_jobs` 和 `show_application_status`；其中后两者优先执行确定性业务服务；
- 搜索与画像读取可并行，之后进入匹配和计划；
- 无画像返回 `needs_profile`；
- 无 LLM Key 时至少支持文档中的两条演示链路；
- Run 可查询、SSE 可恢复、失败有可读错误。

### M5 — Agent Workspace 和投递看板

**任务**：完善 Job Explorer、Profile、Workspace、Applications；任务实时事件、职位结果卡、收藏/待投递交互、手动投递状态与时间线。

**DoD**：
- 完整走通链路 A/B；
- 从 Agent 推荐结果可安全加入待投递清单，不重复写；
- 申请链接跳转到原始站点，界面不声称已自动投递；
- UI 的 loading/error/empty/degraded 状态齐全。

### M6 — 集成、测试、部署文档与回归

**任务**：pytest、前端组件测试、Playwright E2E、最小性能测试、安全回归、DB 迁移回归、README 与功能矩阵更新。

**DoD**：
- `make lint`、`make test`、`make e2e` 可执行；
- README 提供从零启动、seed、真实连接器配置步骤；
- 交付一份 `docs/IMPLEMENTATION_STATUS.md` 列出“已完成/待接入/已知限制”；
- 不把 optional/P1 功能标注为已完成。

### 16.1 统一 Makefile 命令契约

项目必须支持：

```bash
make dev       # 启动开发环境或等价的本地 Docker 环境
make migrate   # 执行 Alembic migrations
make seed      # 导入明确标注的 Demo 数据
make lint      # 后端 ruff + 前端 lint/typecheck
make test      # 后端单元和集成测试 + 前端单元测试
make e2e       # Playwright E2E（测试环境）
make down      # 停止环境
```

如实际使用 pnpm / uv，Makefile 内负责调用；不要要求用户记忆多条零散命令。`README.md` 同时提供不使用 Makefile 的等价命令，兼容 Windows/macOS/Linux 开发。

---

## 17. 前后端协作、提交与完成定义

### 17.1 工程约定

- 后端 Pydantic Schemas 自动生成 OpenAPI；前端采用由 OpenAPI 生成/校验的 Typed API Client，避免前后端 DTO 不一致。
- 强制 formatter/Lint/typecheck，新增公共工具函数写测试。
- 单元测试不得连真实招聘网站或依赖收费 LLM。
- 测试 fixture 不含真实个人敏感信息；开发日志不打印简历正文。
- 模块之间遵守：`Agent -> Tool Adapter -> Service -> Repository`；不要在 Agent Node 中直接创建 SQL。
- 外部调用失败必须返回可观测的错误，而非吞异常返回空列表并宣称没有招聘信息。

### 17.2 每个里程碑的交付格式

Codex 每次完成一个里程碑，向用户报告：

1. 实际完成的功能和对应文件；
2. 执行过的命令及测试结果（没有执行的明确说明）；
3. 如何本地操作验证；
4. 尚未实现或依赖外部条件的功能；
5. 下一里程碑优先任务。

**提交标准**：功能代码 + 迁移 + 测试 + README/文档；不以“页面看起来不错”替代端到端通过。

---

## 18. 可直接复制给 Codex 的第一条开发指令

> 请阅读仓库根目录 `CareerPilot_Codex_Development_Spec_v1.0.md`，以该文档为唯一开发基线。现在从 **M0 项目初始化** 开始，不要一次性跳到 M4/M5。请先检查项目文件结构，生成可运行的 Next.js + FastAPI + PostgreSQL + Redis + Celery Docker Compose 工程，提供 `.env.example`、Makefile、README、基础 CI/Lint/Test、前后端健康检查与初始 Dashboard。默认 `DEMO_MODE=true`，不要求任何外部 API Key。完成后运行可执行的检查并记录在 `docs/IMPLEMENTATION_STATUS.md`；报告完成内容、测试结果、启动方法以及下一步 M1 的实施清单。后续严格按文档 M1–M6 顺序逐项推进。严禁使用伪造岗位作为真实岗位展示，严禁实现自动外部投递。

---

## 19. 权威参考文档（用于实施时核对最新 API）

- LangGraph 官方文档：<https://docs.langchain.com/oss/python/langgraph/overview>
- LangGraph 持久化与中断：<https://langchain-ai.github.io/langgraph/concepts/durable_execution/> 、<https://langchain-ai.github.io/langgraph/concepts/breakpoints/>
- Greenhouse 公开 Job Board API：<https://docs.greenhouse.io/job-board>
- Lever Postings API：<https://github.com/lever/postings-api>
- Ashby 公开 Job Postings API：<https://developers.ashbyhq.com/docs/public-job-posting-api>
- FastAPI：<https://fastapi.tiangolo.com/>
- Next.js App Router：<https://nextjs.org/docs/app>
- SQLAlchemy：<https://docs.sqlalchemy.org/>
- Celery：<https://docs.celeryq.dev/>

> 外部接口、限额和 SDK 版本可能变化；编码时遵循已安装依赖版本的官方文档，不把示例 URL 作为真实可申请岗位，也不将公共职位读取权限误认为申请提交权限。

---

**文档结束。**
