# CareerPilot V2 — 招聘信息聚合与个人求职进度 Agent

版本：2.0（2026-10-21）
状态：产品需求变更与 Codex 实施规范
适用范围：已完成 M0/M1、M2 基础设施已开发但中国互联网大厂官方批量同步受阻的现有仓库

## 0. 给 Codex 的总指令

先阅读仓库中的 `CareerPilot_Codex_Development_Spec_v1.0.md`、`docs/IMPLEMENTATION_STATUS.md`、`docs/M2_CHINA_JOB_SOURCES.md` 及当前源代码。以本文件覆盖旧规范中“站内自动投递、必须有中国大厂官方批量同步 API 才能开展 M3/M4、用户第三方登录后服务端自动获得会话”的部分；与之不冲突的工程、认证、数据隔离和测试要求继续保留。不要整体重构 M0/M1/M2；增量修改并执行迁移和回归测试。每个阶段验收后停止，不自动进入下一阶段。

### 明确的产品目标

用户可在 CareerPilot 中：
1. 跨国内互联网公司搜索实习、暑期实习、校招等公开职位，按关键词、城市、企业、岗位方向、招聘类型、毕业届别过滤。
2. 查看职位标题、JD、来源链接、发现时间、官方发布日期（如有）、来源核验状态，点击前往官方页面自行申请。
3. 上传简历、编辑/确认个人偏好，通过 M3 的可解释规则或启发式匹配查看推荐岗位；当前不进行算法训练、RL 或自定义微调。
4. 管理自己在各公司的申请和状态时间线。系统支持用户手动登记、授权邮箱读取通知、以及未来可选的本地浏览器插件对当前已登录页面的用户触发辅助导入。
5. 用自然语言与 LangGraph Agent 查询“近 7 天发现哪些匹配岗位”“哪些申请有新的已核实通知”等；后续设置定时提醒。

**不实现**：系统内填写或提交投递表单、自动海投、使用 Cookie 代管第三方招聘账号、未经许可的登录后网页批量采集、绕过登录/验证码/风控。

## 1. 产品边界与来源能力矩阵

`JOB_DISCOVERY` 是查找职位；`PERSONAL_PROGRESS` 是读取用户自己的申请状态。两者必须解耦。

| 能力 | 默认路径 | 降级方案 | 数据可信等级 |
| --- | --- | --- | --- |
| 跨公司发现职位 | 获许可的搜索服务 API，限制官方招聘站点域名 | 用户手动提交官方链接 | 仅“发现候选链接”，非官方最新确认 |
| 职位详情 | 允许时访问官方公开职位详情页并结构化解析 | 用户粘贴或导入本人浏览到的 JD | 区分 `verified_official`, `user_provided`, `search_snippet_only` |
| 批量同步 | 仅明确允许的官方 API/页面访问 | 不阻塞搜索发现功能 | 单独验收，不得冒充完成 |
| 个人进度 | 用户授权邮箱只读检索 | 用户手工更新；用户触发浏览器插件 | 区分 `email_confirmed`, `user_reported`, `website_user_confirmed` |
| 官网账号授权 | 真正存在的官方授权 API 才启用 | 不实现虚假“连接成功”；插件模式是独立能力 | 从不因用户打开链接就认定可同步 |

具体支持列表必须逐站维护，记录合规性、访问方式、字段质量、失败原因。搜索引擎的索引不是实时数据库，不能宣传“所有企业完整实时职位”。

## 2. 用户流程

### 2.1 搜索职位

用户输入“上海/北京的 LLM Agent 实习，近七天，优先字节/阿里/百度”：

1. 解析结构化筛选条件。
2. 执行站点限定搜索（只检索经过配置验证的企业官方招聘域名），并可合并已有 Job 数据库中的职位。
3. 规范化 URL 和公司/职位元数据，去重。
4. 能够在站点许可范围内访问详情时解析完整 JD、职位类型、城市与真实日期；否则仅保留 `JobLead` 的官方候选链接及有限摘要。
5. 返回列表，明确展示：**官方已核验** / **待核验** / **用户导入**，以及“首次发现”“官网发布”“最近核验”三种不同时间。禁止把搜索索引时间当职位发布日期。
6. 用户点击“查看官网”进入企业原始招聘页面，自行登录和申请；CareerPilot 不接管登录。

### 2.2 用户记录招聘进度

用户从 CareerPilot 点击外部官网、完成申请后，回到 CareerPilot 点“标记已申请”；允许输入申请日期、官网岗位链接及备注。

- 路径 A：用户显式授权 Gmail 等邮箱的只读访问，定时匹配官方发送的通知邮件。提取公司、岗位、事件类型、发生时间、原始邮件标识；生成**待确认进度事件**或符合规则的已确认事件，用户可修正。
- 路径 B：用户手动更新状态和证据。
- 路径 C（后续独立里程碑）：用户在目标官网自行登录后，点击 Manifest V3 浏览器插件“同步当前页面”。仅在获得当前站点权限、适用站点政策允许、支持相应页面结构时，从用户当前打开的页面抽取状态，向用户展示预览并经确认后上传最小必要字段。禁止上传网站 Cookie、密码、Token，禁止自动后台轮询已登录站点、绕过 CAPTCHA/风控、读取无关私人页面。

不应把某个用户账号授权后的私人数据作为全站公共岗位源。登录成功也不代表站点授予自动数据采集许可。

## 3. 架构调整

维持 Next.js + FastAPI + PostgreSQL + Redis/Celery + LangGraph。由如下组件组成：

- `JobDiscoveryService`：联邦检索适配器，可接入获许可的 Web Search API；标准化查询、域名 allowlist、缓存、分页。
- `JobDetailVerifier`：仅对允许的官方公开详情页进行受控访问、字段解析；否则保留候选链接，不伪装为完整 Job。
- `ManualJobImportService`：接受官方 URL 与用户提供的 JD 文本，执行校验、归属和标准化。
- `JobCatalogService`：使用 M1/M2 的 Job/RawJob/JobSource/SyncRun，增量支持 `JobLead` 和 `SourceEvidence`；现有来源 Connector 可以继续保留。
- `ResumeProfileService / JobMatchService`：M3 简历解析、画像确认、基于明确技能与约束的可解释启发式评分，不在本阶段训练模型。
- `ApplicationTrackingService`：依赖 M1 `Application` / `ApplicationEvent`，实现手动登记、邮件事件与冲突处理；状态变化需记录证据。
- `EmailIntegration`：用户 OAuth 只读授权，按最小范围检索求职通知，严禁将原始邮箱消息默认交给任意外部大模型；敏感字段最小化存储并支持撤销/删除。外部服务的审核要求要单独验证。
- `BrowserCompanion`：可选且独立的 MV3 插件，只在已经核实许可的站点开启；**不属于默认必须交付项**。
- `LangGraph Supervisor`（M4）：负责意图路由和多步对话；底层数据访问必须走确定性的服务和权限检查。专业工作节点：JobDiscovery、JobFilter/Match、ProgressSummary、NotificationSummary。不要为了角色数量而创建一堆虚假 Agent。

## 4. 数据结构增量建议

基于现有 schema 先盘点再创建 Alembic 迁移，避免重复定义：

- `job_leads`：`id`, `company_id`, `title`, `official_url`, `summary`, `source_method`, `first_seen_at`, `last_seen_at`, `last_verified_at`, `verification_status`, `published_date`（原始仅日期时存 DATE 而非伪造 UTC00:00）, `job_id_nullable`, `source_payload_hash`。
- `source_evidence`：`id`, `job_id_nullable`, `lead_id_nullable`, `source_url`, `evidence_kind`, `captured_at`, `evidence_ref`, `verification_method`, `content_hash`。
- `application_events` 增加/复用：`origin`（user/email/browser/official_api）、`confidence`、`occurred_at`、`observed_at`、`reference_id`、`review_required`，在没有证据时状态保持 `unknown` 或 `user_reported`，不得自动变成官方确认。
- `email_connections`（仅在邮箱阶段）：`user_id`, `provider`, `status`, `granted_scope`, `token_secret_ref`, `last_sync_at`；任何 token 不明文写入 ordinary DB/log；没有真实 Secret Manager 时先支持仅本地开发的安全配置，不对外宣布可用。
- 对于 `Application` 现有数据保留兼容，不破坏收藏、已有状态历史以及 User A/B 隔离。

`source_method` 例如 `official_api|official_page|search_discovery|manual_import|email|browser_companion`。将候选搜索结果与已验证职位分开，避免劣质摘要污染 Job 库。

## 5. API 建议（按现有 API 风格做兼容扩展）

- `GET /api/v1/jobs/discover?query=&company=&city=&job_type=&days=`：返回混合 `Job` + `JobLead` 的候选列表及来源可信标识；无真实 Search API 凭据时明确返回“未配置”，但仍可查已有库和手动导入数据，不以 fixture 冒充实时搜索。
- `POST /api/v1/job-leads/import`：官方 URL + 用户粘贴 JD 可选，允许缺字段，进行 URL allowlist / SSRF 校验、所有权与去重。
- `POST /api/v1/job-leads/{id}/verify`：仅在来源许可范围内执行核验，权限/频率控制。
- `GET /api/v1/jobs/{id}`：已核验职位详情与来源证据。
- `POST /api/v1/applications`：用户手动记录自己在官网的投递行为；不能触发外部提交。
- `GET /api/v1/applications`；`GET /api/v1/applications/{id}/events`；`POST /api/v1/applications/{id}/events`：只操作本人的进度。
- `POST /api/v1/mail-connections/start` / `GET .../status` / `DELETE .../{id}`：实际支持的 OAuth provider 上线后开放。
- `POST /api/v1/progress/import-preview` / `POST /api/v1/progress/import-confirm`：可供邮箱/插件结果复核、确认。
- 在 M4 增加 `/api/v1/agent/runs` 或现有 LangGraph 执行端点，不提前实现自动投递工具。

注意 GET 不得改变状态，所有写请求沿用 M1 CSRF/认证要求。账户私有数据严格用户隔离，`job_leads` 的用户导入内容默认私有，不能直接全网共享。

## 6. 分阶段交付（替代旧 M2 API 依赖）

### M2-R1：可用的真实岗位发现 MVP（现在优先）

- 保留现有 M2 Connector 架构与阻塞文档。
- 首先实现一个获许可的站点限定搜索 API 接口（key 配置+可替换 provider），支持字节、腾讯、阿里、百度、美团的**官方招聘域名查询**，先返回候选链接，过滤非官方、异常 URL 和重复。
- 完成 JobLead / SourceEvidence Schema、API、岗位卡片状态标签、外部官网跳转。
- 实现用户提供官方链接和 JD 的导入；没有外部搜索 API key 时，这个真实人工导入链路仍可使用。
- 若有站点许可，可对该站点逐页验证公开详情，并记录可核验比例；没有许可时不批量爬取、不把摘要虚构成完整 JD。
- 实际跑一轮真实发现任务，记录查询、发现数量、核验数量、运行时间、源 URL、失败与限制；固定测试可以用 fixture，不能拿 fixture 当真实结果。
- DoD：至少可真实搜索或导入一批官方岗位候选链接，提供官网直达、可检索和可信标签；原来的“P0 自动批量同步”未完成项继续如实保留。

### M2-R2：个人申请进度管理（可与 M3 排程协同）

- 复用 Application/Event，提供用户在官网申请后手动登记和编辑、来源标记、时间线、过滤与去重。
- 清楚区分用户填报、邮件佐证和官网核验，避免伪造“招聘官网已同步”。
- DoD：能以两个隔离账户分别维护多家公司进度，测试通过。

### M3：简历画像与匹配

- 上传简历、解析技能/项目/学历、用户确认画像。
- 使用启发式规则与关键词等解释匹配结果；候选链接只有标题/摘要时，不对不存在的 JD 做伪评分。缺信息时显示“信息不足”。
- 为匹配结果提供 source/status/score_reason，并保留已申请/收藏状态。
- DoD：从用户简历到官方岗位候选再到可信匹配结果的闭环；不得宣称实时全量。

### M4：多 Agent 查询编排

- LangGraph Supervisor，查询工具与进度总结工具，持久化状态和跨用户隔离。需求示例：“近七天发现字节/百度的实习岗位，排除已申请，给出最匹配的 10 条”“总结我最近收到的面试通知”。
- Agent 不可生成无证据的官网状态，任务失败与信息缺失要明确报告。
- DoD：任务流程端到端、任务恢复、引用源链接、工具错误处理以及运行测试。

### M5：个人进度同步增强、UI 与提醒

- 优先选择用户真实在用且有授权开发接口的邮箱 Provider，上线只读 OAuth 邮件通知解析与状态确认。
- 完整岗位列表、智能对话、我的申请进度看板、信息新鲜度与提醒设置。
- **浏览器插件只作为可选独立 PoC**：先确认目标网站允许此行为，再在用户主动点击时读取当前页面已渲染、与其本人申请有关的最小字段；未经验证不启用。
- DoD：邮件同步真实授权演示（或明确阻塞）、多用户隔离与隐私测试、用户确认机制。

### M6：系统集成与安全性

- E2E、文档、Session/SyncRun 清理、搜索限流/配额、审计、权限、安全与部署监控。
- 将 M2 旧验收中的“官方批量同步”另列为 `blocked/not_supported`，除非得到实际许可并跑通在线验证。

## 7. 关键测试与验收

1. 搜索返回的职位 URL 确为目标公司的经过配置验证的招聘域名，不被开放重定向伪装。
2. 搜索查询的 `days=7` 表示搜索服务或本地发现窗口，**不等于官网发布时间最近七天**；如果用户明确要求“近七天发布”，只有 `published_date` 官方可核实时才能严格过滤。
3. 不存在自动抓取来源时，用户仍可通过手动导入构建真实岗位列表。
4. `JobLead` 缺失完整 JD 时不得伪造职位详情和高精度匹配评分。
5. 允许的详情校验失败不会清空已有数据或把岗位误判关闭。
6. 同一个 URL 重复发现与重复导入幂等，跨源疑似重复有独立标识。
7. 每条数据有 `source_method`, `source_url`, `first_seen_at`, `verification_status`，有官方日期时用 `DATE` 保留原始精度。
8. User A 不可读取 User B 的简历、导入私有 JD、授权信息和申请历史。
9. 用户打开官网链接不改变 CareerPilot 中“已登录/已同步”状态。
10. 没有 OAuth Provider 时 UI 不显示虚假的“已连接招聘账户”。
11. 所有申请进度必须标注 `user_reported`, `email_confirmed`, `website_user_confirmed`, `official_api` 等来源；没有证据不自动变更。
12. 外部搜索失败、配额耗尽和网络超时都有明确错误提示，已有 Job 数据继续可查询。
13. 不包含任何自动提交申请、Cookie 抓取、验证码绕过、登录后后台批量访问功能。
14. M0/M1/M2 回归测试继续通过，文档维护每个里程碑通过与阻塞项。

## 8. 当前立即执行的 Codex 工作范围

1. 先对现有仓库做差异审计，识别可复用的 M1 Jobs/Applications 以及 M2 Connector、RawJob、JobSource、SyncRun。
2. 更新 PRD、架构、`IMPLEMENTATION_STATUS.md`，将自动投递移出产品范围；保留历史代码但隐藏不必要的入口，避免破坏现有数据。
3. **只开发 M2-R1：官方招聘站点限定发现 + 候选岗位（JobLead）与已验证 Job 区分 + 手动官方链接/JD 导入 + 来源新鲜度显示 + 前后端最小可用链路。**
4. 搜索 API 必须允许环境变量配置，不得硬编码 key；可替换 provider、限流、缓存、超时和错误处理。
5. 严格执行真实在线验证，报告真实候选链接数量、来自哪个官方域名、核验状态与测试结果；如外部服务受限，不伪造真实成功。
6. `make migrate`, `make lint`, `make test` 与实际服务端联调完成后停止，输出已知限制与 M2-R2 计划，不自动进入 M3。
