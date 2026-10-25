# CareerPilot · 智能求职 Agent

面向国内互联网实习 / 校招的岗位搜索、简历画像、可解释匹配与多 Agent 求职工作流。

> **当前状态：M1–M6 完成（个人版）——可视化工作台 + 异步 LangGraph Agent + SSE + QQ/Gmail 同步 + 本地备份恢复。**
> 已具备账号认证（限流 + CSRF）、用户隔离、岗位库、收藏、待投递清单、个人申请时间线，
> Connector / SyncRun / Celery 同步管线；M2-R3 多企业搜索与单岗位详情核验；
> M3 的 PDF/DOCX 简历解析、画像确认、JD 特征提取与 `heuristic_v1` 可解释匹配；
> M4 的 Supervisor + 四个专业 Agent + 10 个受限工具 + PostgreSQL Checkpointer + `/agent` 页面；
> M5 的邮件连接与招聘事件同步、看板/日历等前端工作台；
> M6 的 Agent 异步执行（202 + Worker）、`request_id` 幂等、SSE 断线续传与轮询降级、
> 协作式取消与超时、本地备份/恢复脚本与个人版部署脚本。
>
> **如何启动：见下方 [正式启动](#正式启动个人版)；如何使用：见 [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)。**
> **二次开发 / AI 接手：先读 [`AGENTS.md`](AGENTS.md)。**
> 开发基线：`CareerPilot_Codex_Development_Spec_v1.0.md` + 产品变更
> [`CareerPilot_Revised_Product_M2_M4_Spec_v2.md`](CareerPilot_Revised_Product_M2_M4_Spec_v2.md)，
> 状态与评估见 [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)。

## 技术栈

| 层级 | 选型 |
|---|---|
| Web | Next.js 16（App Router）、React 19、TypeScript 5、Tailwind CSS 4 |
| API | Python 3.12+、FastAPI、Pydantic v2 |
| 数据库 | PostgreSQL 16（pgvector 镜像）+ SQLAlchemy 2 + Alembic |
| 认证 | Argon2 + PostgreSQL 服务端会话 + HttpOnly Cookie + Origin/CSRF Token + Redis 登录限流 |
| 缓存 / 队列 | Redis 7 + Celery 5 Worker + Beat 调度 |
| 数据接入 | Connector Protocol / RawJob / SyncRun / SSRF 防护的 HTTP 客户端 |
| 测试 | pytest、Vitest、Testing Library、Playwright |
| 容器 | Docker Compose（`web` / `api` / `worker` / `scheduler` / `postgres` / `redis`） |

实测版本固定在 `backend/requirements*.txt` 与 `apps/web/package-lock.json`，记录见状态文档。

## 目录结构

```text
CareerPilot/
├── apps/web/                    # Next.js App Router
│   ├── app/(app)/               # 受保护页面：dashboard / jobs / discover / resumes / profile
│   │                            # matches / agent / applications / calendar / saved-jobs / settings
│   ├── app/login/               # 登录与注册
│   ├── components/              # App Shell、岗位卡片、状态控件
│   ├── lib/                     # Typed API client、SSE 跟随、筛选与展示映射
│   └── tests/                   # Vitest + Testing Library（34 项）
├── backend/
│   ├── alembic/                 # 数据库迁移
│   ├── app/
│   │   ├── api/v1/              # auth / profile / jobs / discovery / leads / saved / applications
│   │   │                        # resumes / matches / mailboxes / agent / agent_runs / system
│   │   ├── agents/              # Supervisor、专业 Agent、工具、run_service（状态机）
│   │   ├── auth/                # 密码哈希、会话、当前用户与管理员依赖
│   │   ├── connectors/          # Protocol、SafeHttpClient、百度公开页面、fixture/manual/alibaba
│   │   ├── mailboxes/           # IMAP / Gmail 客户端、增量游标、加密凭据
│   │   ├── search/              # 搜索 provider、官方域名 allowlist、发现服务
│   │   ├── core/                # 配置、日志、错误、文本归一化
│   │   ├── db/                  # Engine、Session、模型、Demo seed
│   │   ├── repositories/        # ORM 数据访问（用户资源按 user_id 过滤）
│   │   ├── schemas/             # Pydantic 契约
│   │   ├── security/            # CSRF、登录限流
│   │   ├── services/            # 领域逻辑、同步、标准化/去重
│   │   ├── storage/             # FileStorage 抽象
│   │   └── workers/             # Celery 任务与 Beat 调度
│   ├── fixtures/demo_jobs.json  # 8 条明确标注的演示岗位
│   └── tests/                   # 238 项后端测试
├── scripts/                     # start / stop / status / backup / restore
├── infra/                       # Dockerfile.api / Dockerfile.web
├── docs/                        # 实施状态、M2–M6 设计与评估
├── docker-compose.yml
├── .env.example
├── AGENTS.md                    # 二次开发 / AI 接手须知
└── Makefile
```

分层：`API → Service → Repository → DB`；用户资源查询必须携带认证上下文中的 `user_id`。

## 正式启动（个人版）

### 前置条件

- Docker Desktop 或 Docker Engine + Compose v2（`docker compose version` 能输出版本）；
- 空闲端口：`3000`（Web）、`8000`（API）、`5432`（PostgreSQL）、`6379`（Redis）；
- 一个 OpenAI-compatible LLM（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`），否则 `/agent` 不可用；
- 可选：Tavily Key（在线岗位搜索）、QQ 邮箱 IMAP 授权码、Google OAuth 凭据（Gmail）。

### 1. 准备 `.env`

```bash
cp .env.example .env      # 或 make env
```

先生成两个本地密钥（`cryptography` 由 `make setup` 安装；也可用
`docker compose run --rm --no-deps api python -c "..."` 执行同样的代码）：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"          # → SESSION_SECRET
backend/.venv/bin/python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # → MAILBOX_SECRET_KEY
```

至少填写以下四项，其余保持默认即可：

```dotenv
# 会话签名密钥（≥32 位随机串）
SESSION_SECRET=<上一条生成的随机串>

# 邮箱凭据加密密钥（Fernet，44 字符 base64）
MAILBOX_SECRET_KEY=<上一条生成的 Fernet key>

# LLM（三者缺一则 Agent 页面提示不可用）
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

> `MAILBOX_SECRET_KEY` 一旦用于加密邮箱凭据就不能更换/丢失，否则已连接的邮箱需要重新授权。
> 真实密钥只放在 `.env` 中；`.env` 已被 Git 忽略，禁止提交。
> 若希望 `/discover` 走在线搜索，再补 `TAVILY_API_KEY`；只使用演示数据可留空。

### 2. 启动

```bash
make dev              # 构建并后台启动 web / api / worker / scheduler / postgres / redis
make migrate          # Alembic upgrade head
make seed             # 可选：导入 8 条 is_demo=true 演示岗位
```

或用一键脚本（会先校验 `.env` 关键变量、等待全部服务 healthy）：

```bash
./scripts/start.sh
```

`make dev` **不会**自动迁移，新环境必须按 `dev → migrate → seed` 顺序执行。
首次构建需要数分钟（npm 走 `registry.npmmirror.com` 镜像 + BuildKit 缓存）。

### 3. 确认服务健康

```bash
docker compose ps                 # 6 个服务应为 running / healthy
curl -s localhost:8000/readyz     # {"status":"ready", ...}
./scripts/status.sh               # 容器 + 邮箱同步 + 最近 Agent run 统计
```

| 地址 | 说明 |
|---|---|
| <http://localhost:3000> | Web 入口（未登录会跳转 `/login`） |
| <http://localhost:8000/readyz> | PostgreSQL / Redis 就绪 |
| <http://localhost:8000/healthz> | 进程存活 |
| <http://localhost:8000/docs> | OpenAPI（`APP_ENV=production` 时关闭） |

停止：`./scripts/stop.sh` 或 `make down`（保留数据卷）。日志：`make logs`。
**不要**用 `docker compose down -v` 做“重启”，它会删除数据库卷。

## 首次使用流程

> 完整的**使用者手册**（每个页面做什么、按钮在哪、失败怎么处理、常见问题）见
> **[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)**。本节只保留最短闭环，用于部署后确认服务可用。

1. **注册登录** — <http://localhost:3000/login>（密码 ≥ 8 位，邮箱统一转小写）。
2. **简历 → 画像** — `/resumes` 上传 PDF/DOCX（默认 ≤ 10 MB）→ `/profile` 核对教育/技能/经历/偏好 →
   点**确认画像**。未确认时推荐与 Agent 匹配都会要求先确认，不会给出分数；修改画像后需重新确认。
3. **找岗位 → 记进度** — `/discover`（官方站点直连检索）或 `/matches`（基于画像的推荐）找到岗位 →
   收藏或「登记申请进度」→ 在 `/applications/{id}` 维护状态、登记笔试/面试预约 →
   `/calendar` 只显示这些**预约**（不显示投递、初筛等状态变更）。
4. **可选** — `/agent` 多轮问答（异步执行、实时进度、可停止）；`/settings/email` 连接邮箱
   （QQ IMAP 授权码 / Gmail 需自备 OAuth 凭据），同步只产生「待确认」候选。

启动后最容易卡住的三点：

- `.env` 缺 `SESSION_SECRET` / `MAILBOX_SECRET_KEY` → 登录会话或邮箱凭据不可用；
- 未执行 `make migrate`（`alembic upgrade head`）→ 页面能打开但接口报 500；
- 未配置 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` → 只有 `/agent` 不可用，其余功能正常。

全程**不会**自动投递、自动填表或代登录招聘平台。

### 发现与导入岗位（M2-R1）

> 页面上的操作细节（多选企业、交接给 Agent、私有 JD 一键登记到看板）见手册 6.1–6.3。

登录后打开 <http://localhost:3000/discover>：

页面有两个入口：

**企业官网直连检索**（已支持腾讯 / 京东 / 字节跳动 / 小红书 / 哔哩哔哩 / 美团 / MiniMax）

- 服务端浏览器把关键词输入官方搜索框，读取标题、城市、招聘类型与完整 JD；
- 不消耗搜索额度、不依赖 `TAVILY_API_KEY`；仅覆盖校招 / 实习（美团先切「应届校招」）；
- 「跟随上方筛选」把筛选里勾选的企业自动带入直连（手动点选后关闭跟随）；
- 「腾讯招聘项目」只在选中腾讯时显示；
- 腾讯与京东走官方 JSON 接口，其余 5 家走服务端浏览器渲染；
- 其余 12 家在页面上是灰色锁定按钮：点击会打开该企业官网校招搜索页（新标签），
  提示把链接 / JD 粘到「导入岗位」；悬停给出未适配原因（需登录 / 接口未公开 / 结构不稳定）。

**筛选与搜索**

1. 选择企业（19 家，默认 10 家 P0）、关键词、城市、实习/校招、岗位方向、发现窗口与排序；
2. 走搜索索引（需 `TAVILY_API_KEY`）；无 Key 时该路径不可用，改用直连检索或手动导入；
3. 搜索结果只生成 `JobLead` 候选链接；点击“查看官网”前往官方站点自行申请；
4. 候选可点击“尝试核验”，成功后才进入已核验 `Job` 库并记录来源证据；
5. 未核验候选保留“待核验”，不会伪造完整 JD；
6. 分页展示候选与已核验岗位；Provider 状态明确显示不可用原因。

> 页面底部「询问 Agent」会带上关键词/企业/城市/类型/方向（不含直连开关）。

手动导入：<http://localhost:3000/import>

- 两种模式：**官方链接解析**（百度用站点解析器写入公开岗位库；其他企业用无头浏览器读取
  详情页并给出待确认草稿）；**粘贴 JD（任意企业）** → 私有候选；
- 粘贴模式对域名不设限（不做抓取与核验），未适配直连的企业都走这条；
- 页面不可读时可粘贴 JD，保存为**仅本人可见**的候选，标记“用户导入”；
- 同一链接重复导入幂等，不会自动投递或登录第三方账号。

### 记录个人申请进度（M2-R2）

打开 <http://localhost:3000/applications>：

1. 从岗位/发现页点击“已申请，登记进度”，或使用“仅登记官方链接”；私有 JD 详情可一键登记到看板；
2. 在官网自行登录、申请，回到这里更新状态；
3. 可上传 `.eml` 招聘通知：系统只生成预览，确认后才写入时间线；
4. 打开某条申请可登记**笔试/面试预约**（「新增一轮」与「改期（仅替换选中的那条预约）」），取消后日历不再显示但时间线保留；
5. 邮件未明确说明的状态不会被自动推断；重复邮件不会重复导入；
6. 打开官网不会自动把状态改为“已申请”。

> 不托管招聘平台密码/Cookie，不自动投递、不自动填表。招聘**邮箱**连接是另一条链路：
> QQ 走 IMAP 授权码、Gmail 走 OAuth（需自备 Google 凭据），见 `/settings/email`。

### 管理数据源同步（M2）

`ADMIN_EMAILS` 为空时任何人都不能触发同步。设置管理员邮箱后重启 API：

```dotenv
# .env
ADMIN_EMAILS=admin@example.com
```

1. 用该邮箱注册账号；
2. `GET /api/v1/job-sources` 查看数据源与健康状态；
3. 生产/真实同步需在 `.env` 提供 `ALIBABA_APP_KEY`、`ALIBABA_APP_SECRET`、
   `ALIBABA_TENANT_ID`、`ALIBABA_POSITION_URL_TEMPLATE`，并启用该来源；
4. `POST /api/v1/job-syncs`（需 CSRF Token）触发 Celery 任务；
5. `GET /api/v1/job-syncs/{id}` 查看 fetched / created / updated / failed。

> 岗位发现（直连检索 / 搜索索引 / 手动导入）与 Celery 来源同步是两条独立链路；后者仍只对已配置来源生效。
> 默认只有 `fixture`（演示）来源启用，阿里/百度/手工来源保持禁用或仅用于显式导入。

| 页面 | 说明 |
|---|---|
| `/login` | 登录 / 注册 |
| `/dashboard` | 工作台：真实统计、最新岗位、最近进度、即将开始 |
| `/jobs` | 已核验岗位库（需登录） |
| `/discover` | 官方站点限定发现 + 候选链接 + 核验 |
| `/import` | 导入官方岗位链接 / 私有 JD |
| `/resumes` | 简历上传、解析、设为画像来源 |
| `/profile` | 画像与求职偏好编辑、确认画像（含未保存草稿提示与恢复） |
| `/matches` | 个性化推荐 + 单岗位可解释匹配 |
| `/saved-jobs` | 收藏 / 待投递清单 |
| `/applications` | 申请列表/表格/看板、时间线、`.eml` 导入；详情可登记/改期/取消预约 |
| `/calendar` | 面试日程：只显示已预约的笔试/面试，支持月/周/列表 |
| `/agent` | 多 Agent 工作流（异步 + SSE 进度、可停止、刷新恢复） |
| `/settings/email` | 邮箱连接、测试、立即同步、候选确认 |

## 本地开发（不使用 Docker 运行应用）

前置条件：Python 3.12+、Node.js 22+、npm，以及可用的 PostgreSQL 与 Redis。

```bash
docker compose up -d --wait postgres redis
make setup                      # backend/.venv + npm ci
```

本地通过 `localhost` 连接数据库：在 `backend/` 下运行时，若未设置 `DATABASE_URL`，默认使用
`postgresql+psycopg://career:career_dev_only@localhost:5432/careerpilot`。

```bash
# 迁移与 Demo 数据
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python -m app.db.seed

# 后端
.venv/bin/uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd apps/web
API_INTERNAL_URL=http://localhost:8000 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

## 常用命令

| 命令 | 作用 |
|---|---|
| `make help` | 列出全部 target |
| `make env` | 不存在 `.env` 时从模板生成 |
| `make dev` | 构建并后台启动全部服务 |
| `make migrate` | 在容器内执行 `alembic upgrade head` |
| `make seed` | 导入明确标注的 Demo 数据（幂等，生产拒绝） |
| `make down` / `make logs` / `make ps` | 停止（保留卷）/ 跟踪日志 / 查看健康状态 |
| `make build` | 重新构建镜像 |
| `make lint` | 后端 ruff check + format check、前端 ESLint + `tsc --noEmit` |
| `make test` | 后端 pytest + 前端 Vitest |
| `make test-backend` / `make test-web` | 单独跑后端 / 前端测试 |
| `make e2e` | Playwright 端到端（需先启动服务） |
| `make smoke` | 真实外部服务冒烟提示（Tavily / QQ IMAP / Gmail / LLM） |
| `make clean` | 删除本地构建产物（不动 Docker 数据卷） |
| `./scripts/start.sh` / `stop.sh` / `status.sh` | 个人版启动 / 停止 / 健康与运行状态 |
| `./scripts/backup.sh` / `restore.sh` | 备份 / 恢复（见下节） |

后端测试需要 PostgreSQL（默认 `careerpilot_test`，可用 `TEST_DATABASE_URL` 覆盖）；
测试会自动创建数据库、重置 schema 并执行真实 Alembic 迁移。
当前基线：后端 238 项、前端 34 项全部通过，Playwright 异步 Agent 路径通过。

## 备份与恢复

```bash
./scripts/backup.sh                                    # 生成 backups/<时间戳>/
ls backups/<时间戳>                                     # database.sql / uploads.tar.gz / MANIFEST.sha256
./scripts/restore.sh --from backups/<时间戳> --dry-run  # 预演，不写库
./scripts/restore.sh --from backups/<时间戳>            # 默认恢复到 careerpilot_restore_test
./scripts/restore.sh --from backups/<时间戳> --force    # 覆盖真实库（危险，需手动输入库名确认）
```

备份内容与纪律：

- `database.sql`：一致性 `pg_dump`（不是直接拷数据目录）；
- `uploads.tar.gz`：简历等私有文件；
- `mailbox_secret.key`：Fernet 密钥（600），**必须与 SQL dump 分开保管**，否则恢复后邮箱凭据不可解；
- `MANIFEST.sha256` 校验和；失败时不会覆盖上一份可用备份；默认保留最近 7 份（`BACKUP_KEEP`）。

## 已实现 API（`/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/register` | 注册并建立会话（Argon2 + HttpOnly Cookie） |
| POST | `/auth/login` | 登录（失败计入限流） |
| POST | `/auth/logout` | 撤销当前会话（需 CSRF） |
| GET | `/auth/me` | 当前用户 |
| GET | `/auth/csrf` | 获取/轮换 CSRF Token |
| GET/PATCH | `/profile/me` | 画像与求职偏好，版本号自增；内容变更会失效「已确认」 |
| POST | `/profile/confirm` | 确认画像（推荐与 Agent 匹配的前置条件） |
| POST | `/profile/apply-resume` | 用简历解析结果覆盖画像草稿 |
| POST/GET/DELETE | `/resumes` | 上传（PDF/DOCX，默认 ≤ 10 MB）/ 列表 / 删除 |
| GET | `/resumes/{id}` | 单份简历（解析状态与文本） |
| POST | `/resumes/{id}/primary` | 设为画像主要来源 |
| GET | `/jobs` | 搜索：`q`/`keyword`、`companies`、`cities`、`job_types`、`source_types`、`recruitment_program`、`is_demo`、时间、`status`、`sort`、分页 |
| GET | `/jobs/{id}` | 岗位详情（原始 JD、来源、时间） |
| POST/DELETE | `/jobs/{id}/save` | 收藏 / 待投递，按 `list_type` 幂等 |
| GET | `/jobs/discover` | 已有岗位 + 官方候选链接 + Provider 状态；支持 `companies`、`city`、`job_type`、`job_family`、`sort`、`page` |
| POST | `/job-imports/preview` | 解析用户提交的百度官方详情页（不写库） |
| POST | `/job-imports` | 官方页面确认导入（粘贴 JD 请走 `/job-leads/import`） |
| GET | `/job-imports/capabilities` | 当前支持的导入方式 |
| GET | `/job-leads` | 公开候选 + 当前用户私有候选 |
| GET | `/job-leads/sources` | 已在线校验的 P0/P1 官方招聘来源目录 |
| POST | `/job-leads/import` | 官方 URL + 可选 JD，保存为私有候选 |
| GET | `/job-leads/{id}` | 候选详情：来源证据、核验失败原因、是否私有 |
| POST | `/job-leads/{id}/verify` | 单岗位官方/可信 ATS 详情核验（Tavily Extract） |
| GET | `/saved-jobs` | 收藏与待投递清单 |
| POST | `/applications` | Job / JobLead / 官方链接登记（重复返回 409 + 已有 id） |
| GET | `/applications` | 申请列表，支持 `status`、`company`、`query` |
| GET | `/applications/{id}` | 详情 + 完整状态时间线 |
| PATCH | `/applications/{id}` | 更新备注/外部岗位信息 |
| GET | `/applications/{id}/events` | 状态事件 |
| POST | `/applications/{id}/events` | 用户确认的进度事件（来源 reference 幂等）；`reschedule_event_id` 指定被替换的预约，`supersede_scheduled` 仅在同类型唯一时兼容 |
| POST | `/applications/{id}/events/{event_id}/cancel` | 取消一条预约（不删历史，只作废日程） |
| PATCH | `/applications/{id}/status` | 兼容旧客户端的条件更新 |
| DELETE | `/applications/{id}` | 删除记录及事件 |
| POST | `/application-imports/email` | 上传 `.eml`，仅生成预览 |
| GET | `/application-imports` / `/{id}` | 当前用户的邮件导入记录 |
| POST | `/application-imports/{id}/confirm` | 用户确认后写入进度（幂等） |
| GET | `/job-sources` | 数据源列表与最近同步状态（登录） |
| GET | `/job-sources/{id}` / `/health` | 数据源详情 / 连接器健康（登录） |
| PATCH | `/job-sources/{id}` | 管理员启用/配置来源（不含密钥） |
| POST | `/job-syncs` | 管理员触发 Celery 同步（202，需 CSRF） |
| GET | `/job-syncs` / `/job-syncs/{id}` | 管理员查看同步审计 |
| GET | `/matches/recommendations` | 个性化推荐（需已确认画像，否则 409 `PROFILE_NOT_CONFIRMED`） |
| POST | `/matches/jobs/{job_id}` | 单岗位可解释匹配（同一画像闸门） |
| POST | `/matches/job-leads/{lead_id}` | JobLead 基础匹配（不输出百分制得分） |
| GET | `/dashboard/summary` | 工作台真实统计 + 最新岗位 + 最近进度 + 即将开始 |
| GET | `/dashboard/calendar` | 面试日程：`from`/`to`，只返回未被作废的笔试/面试预约 |
| POST/GET | `/mailboxes` / `/mailboxes/qq/connect` | 邮箱连接（QQ IMAP 授权码） |
| GET | `/mailboxes/gmail/authorize` / `/gmail/callback` | Gmail OAuth（未配置时明确返回） |
| POST | `/mailboxes/{id}/test` / `{id}/sync` | 测试连接 / 立即同步 |
| GET | `/recruitment-email-candidates` | 待确认招聘事件 |
| POST | `/recruitment-email-candidates/{id}/confirm` / `discard` | 确认写入时间线 / 忽略 |
| POST/GET | `/agent/threads` | 新建/列出 Agent 会话 |
| GET | `/agent/threads/{id}/messages` | 读取会话历史消息 |
| GET | `/agent/threads/{id}/runs` | 会话最近 N 次 run（刷新后恢复订阅与等待状态） |
| POST | `/agent/threads/{id}/runs` | 提交消息并同步执行（兼容旧路径） |
| POST | `/agent/threads/{id}/resume` | 从 Human-in-the-Loop 中断恢复（异步入队） |
| POST | `/agent/runs` | **异步提交** Agent 任务（202，`request_id` 幂等） |
| GET | `/agent/runs/{id}` | 查询 run 状态、结果与错误摘要 |
| GET | `/agent/runs/{id}/events` | 事件回放（`?after=<sequence>`） |
| GET | `/agent/runs/{id}/stream` | SSE 事件流，支持 `Last-Event-ID` 断线续传 |
| POST | `/agent/runs/{id}/cancel` | 协作式取消（只置 `cancel_requested_at`） |
| GET/POST | `/external-accounts` | 当前用户的外部账号连接元数据 |
| DELETE | `/external-accounts/{id}` | 撤销连接并清空密钥引用 |
| GET | `/system/info` | 运行模式（公开、无敏感信息） |

约定：分页响应为 `{"data": [...], "meta": {"page", "page_size", "total"}}`；错误统一为
`{"error": {"code", "message", "details"}}`；时间为 ISO 8601 UTC；每个响应带 `X-Request-ID`。

## 数据库表

`users`、`user_sessions`、`candidate_profiles`、`job_preferences`、`companies`、`job_sources`、
`jobs`、`job_leads`、`source_evidence`、`saved_jobs`、`applications`、`application_events`、
`application_imports`、`sync_runs`、`external_account_connections`、`resumes`、`match_records`、
`agent_threads`、`agent_runs`、`agent_run_events`、`mailbox_connections`、`mailbox_sync_cursors`、
`mailbox_sync_runs`、`recruitment_event_candidates`。

关键约束：

- `users.email` 唯一（服务端统一转小写）；
- `jobs(source_id, source_job_id)` 唯一，`source_url` 必须为 http/https；
- `saved_jobs(user_id, job_id, list_type)` 唯一；
- `applications(user_id, job_id)` 唯一，状态变更与事件在同一事务提交；
- `agent_runs(user_id, request_id)` 唯一（幂等闸门），终态不可回退；
- `agent_run_events(run_id, sequence)` 唯一，只追加不修改；
- 所有用户资源查询都附加 `user_id`，跨用户资源返回 404。

## 关键环境变量

完整模板见 [`.env.example`](.env.example)。

| 变量 | 说明 |
|---|---|
| `APP_ENV` / `DEMO_MODE` | 生产禁止 Demo；生产强制强 `SESSION_SECRET` |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` / `COOKIE_DOMAIN` | Cookie 安全属性（生产默认 Secure） |
| `CSRF_TRUSTED_ORIGINS` | 写操作可信来源（JSON 数组；默认前端 + API） |
| `LOGIN_RATE_LIMIT_IP_*` / `LOGIN_RATE_LIMIT_ACCOUNT_*` | 登录限流窗口与阈值 |
| `TRUST_PROXY_HEADERS` | 仅在受信反向代理后设为 true |
| `ADMIN_EMAILS` | 可触发数据源同步的管理员邮箱（逗号分隔，空=无人） |
| `EXTERNAL_AUTH_ALLOWED_PROVIDERS` / `EXTERNAL_AUTH_ALLOW_BROWSER_SESSION` | 外部账号连接 allow-list；默认全部关闭 |
| `ALIBABA_APP_KEY` / `ALIBABA_APP_SECRET` / `ALIBABA_TENANT_ID` | 阿里官方 TOP API 凭据（未提供则来源未配置） |
| `JOB_SYNC_ENABLED` / `JOB_SYNC_INTERVAL_MINUTES` | Celery Beat 定时同步开关与周期 |
| `CONNECTOR_*` | 外部请求超时、重试、退避、最小间隔、分页与响应体上限 |
| `MANUAL_IMPORT_DIR` | 管理员授权 JSON 导入目录 |
| `SEARCH_PROVIDER` | `none` 或 `tavily`；仅 Tavily 搜索 API |
| `TAVILY_API_KEY` | Tavily key，只从环境变量读取，不写日志 |
| `TAVILY_SEARCH_DEPTH` / `TAVILY_MAX_RESULTS` | 搜索深度、最大结果数 |
| `SEARCH_MAX_QUERIES_PER_REQUEST` / `SEARCH_MAX_CONCURRENT_REQUESTS` | 单次请求查询预算；当前实际顺序执行 |
| `TAVILY_EXTRACT_DEPTH` / `TAVILY_EXTRACT_DAILY_BUDGET` / `TAVILY_EXTRACT_CACHE_TTL_SECONDS` | Tavily Extract 深度、每日预算、缓存时长 |
| `SEARCH_DAILY_BUDGET_PER_PROVIDER` / `SEARCH_RATE_LIMIT_PER_MINUTE` / `SEARCH_TIMEOUT_SECONDS` | 每日请求预算、分钟限流、超时 |
| `SEARCH_CACHE_TTL_SECONDS` | Tavily 结果 Redis 缓存时长 |
| `OFFICIAL_SITE_DISCOVERY_ENABLED` | 是否启用官方站点发现兜底（搜索不可用时的官方来源） |
| `LEAD_VERIFY_RATE_LIMIT_PER_MINUTE` | 候选核验频率限制 |
| `MAX_RESUME_MB` | 简历文件大小上限，默认 10 MB |
| `FILE_STORAGE_DIR` | 简历私有存储目录（本地文件系统） |
| `LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compatible LLM 配置，缺一则 Agent 不可用 |
| `AGENT_MAX_TOOL_CALLS` / `AGENT_MAX_GRAPH_STEPS` / `AGENT_MAX_RUNTIME_SECONDS` / `AGENT_MAX_SEARCH_CALLS` | Agent 运行预算 |
| `MAILBOX_SECRET_KEY` | Fernet 密钥（必须自行生成，禁止提交到 Git） |
| `MAILBOX_SYNC_INTERVAL_MINUTES` / `MAILBOX_SYNC_LOOKBACK_DAYS` / `MAILBOX_SYNC_MAX_MESSAGES` | 邮箱同步频率与范围 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_OAUTH_REDIRECT_URI` | Gmail OAuth（缺失时明确不可用） |

## 数据真实性与安全

- Demo 岗位全部 `is_demo=true`，公司名带“（演示）”，链接位于 `demo.example.org`；
  `DEMO_MODE=false` 时 `GET /jobs` 不返回 Demo 岗位，收藏/投递也拒绝 Demo 岗位。
- `published_at` 缺失时显示“未知”，绝不使用 `first_seen_at` 冒充发布时间。
- 不自动向招聘网站投递，不绕过验证码/登录；投递状态只能由用户手动更新。
- 百度导入只读取用户提交的单个公开详情页；`source_method`、`verification_status`、`verified_at`
  随岗位保存，页面解析失败时不会伪造为已核验。
- 外部账号连接只保存 `vault://`/`secret://` 密钥引用，不保存密码、Cookie 或 Token。
- 密码使用 Argon2；会话令牌仅以 SHA-256 哈希入库；Cookie 为 `HttpOnly` + `SameSite`，
  生产环境自动启用 `Secure`；登录/注册轮换 Session 与 CSRF Token。
- 写操作要求可信 `Origin` 与 `X-CSRF-Token` 双提交校验；登录/注册按 IP 与账号双维度限流。
- Connector 仅访问白名单域名、拒绝内网/回环/云元数据地址、限制重定向/超时/响应体与请求频率。
- 日志不记录密码、Cookie、简历正文；错误响应不暴露堆栈或数据库细节。

## 已知限制

- **M2-R3 搜索 API 仅 Tavily**：其他搜索 API 已删除；无 Tavily Key 时明确不可用；
- 在线搜索（Tavily）只是站外补充；腾讯 / 字节跳动 / 小红书 / 哔哩哔哩 / 美团支持官方直连检索（服务端渲染抓取），其余企业（阿里、得物、DeepSeek、360 等）依赖搜索索引或手动导入；
- 直连检索只覆盖校招 / 实习（美团先切「应届校招」，不含社招），返回条数以官方页面为准，不承诺固定数量；
- 搜索摘要不进入 Job 库；只有成功读取官方详情页后才写入完整岗位；
- 阿里官方 API 需要企业凭据，未配置时该来源不可用；
- 邮件状态提取依赖文本规则，不能保证识别所有企业模板；无法确定时必须人工确认；
- 邮件正文摘要保存在用户私有数据库，未做字段级加密；
- `.eml` 批量导入仍是文件上传方式；IMAP / Gmail 同步已可用，但需自备授权码或 Google OAuth 凭据，浏览器插件未实现；
- 外部账号连接仅有模型/服务/API，未接入真实 OAuth 或浏览器会话 provider；密钥引用依赖部署方接入 Vault/Secret Manager；
- DNS 校验与实际连接之间仍存在理论上的 rebinding 窗口，已限制域名/重定向/私网地址但未做到 IP 固定绑定；
- Agent 事件暂未提供 `answer.delta` 流式 token 与完整 `plan.created` / `tool.started` 图内事件；
- 过期 Session 物理清理、来源定时健康探测仍依赖手动排除；
- 备份恢复的“真实断电 / Worker 强杀”只在代码级闸门与单测层面验证，未做破坏性演练；
- 跨站部署需配置 `COOKIE_DOMAIN`、`CSRF_TRUSTED_ORIGINS`、`CORS_ORIGINS`；
- `GET /jobs` 仍为 ILIKE 搜索，未启用 `pg_trgm` / 中文分词 / 向量召回；
- 只有标题/摘要的 `JobLead` 不参与高精度 JD 评分，必须先核验成 `Job`；
- 不实现自动投递、自动填表、招聘平台密码/Cookie 托管或登录态批量采集。

## 故障排查

| 现象 | 排查 |
|---|---|
| 页面打不开 | `docker compose ps`；`docker compose logs -f web` |
| API 500 / 连不上库 | `curl localhost:8000/readyz`；`docker compose logs -f api postgres` |
| 登录一直失败 | 检查 Cookie 是否因 `APP_ENV=production` + http 被判 `Secure`；查看限流阈值 `LOGIN_RATE_LIMIT_*` |
| 写操作 403 | 缺少 `X-CSRF-Token` 或 Origin 不在 `CSRF_TRUSTED_ORIGINS` |
| `/agent` 提示不可用 | `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 缺一；看 `docker compose logs worker` |
| Agent 一直 `queued` | Worker 未起或 Redis 不可达：`celery -A app.workers.celery_app inspect ping` |
| Agent 事件不刷新 | 反向代理缓冲未关；前端应已自动降级为轮询 |
| 邮箱同步报凭据错误 | `MAILBOX_SECRET_KEY` 与连接时不一致，或授权码已失效，需重新连接 |
| 迁移失败 | `docker compose run --rm --no-deps api alembic current`，不要手改已应用的迁移 |

## 文档索引

- **使用者手册**：[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)
- 状态总览：[`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)
- 接手开发：[`AGENTS.md`](AGENTS.md)
- 搜索与核验：[`docs/M2_CHINA_JOB_SOURCES.md`](docs/M2_CHINA_JOB_SOURCES.md)、
  [`docs/M2_R3_SEARCH_EVALUATION.md`](docs/M2_R3_SEARCH_EVALUATION.md)
- 画像与匹配：[`docs/M3_ARCHITECTURE.md`](docs/M3_ARCHITECTURE.md)、
  [`docs/M3_MATCHING_DESIGN.md`](docs/M3_MATCHING_DESIGN.md)
- Agent：[`docs/M4_AGENT_ARCHITECTURE.md`](docs/M4_AGENT_ARCHITECTURE.md)、
  [`docs/M4_AGENT_WORKFLOWS.md`](docs/M4_AGENT_WORKFLOWS.md)
- 前端与邮件：[`docs/M5_FRONTEND_ARCHITECTURE.md`](docs/M5_FRONTEND_ARCHITECTURE.md)、
  [`docs/M5_USER_FLOWS.md`](docs/M5_USER_FLOWS.md)、[`docs/M5_EMAIL_SYNC.md`](docs/M5_EMAIL_SYNC.md)
- 异步与运维：[`docs/M6_AGENT_ASYNC.md`](docs/M6_AGENT_ASYNC.md)、
  [`docs/M6_SSE_AND_IDEMPOTENCY.md`](docs/M6_SSE_AND_IDEMPOTENCY.md)、
  [`docs/M6_BACKUP_RECOVERY.md`](docs/M6_BACKUP_RECOVERY.md)、
  [`docs/M6_PERFORMANCE.md`](docs/M6_PERFORMANCE.md)、
  [`docs/M6_PERSONAL_DEPLOYMENT.md`](docs/M6_PERSONAL_DEPLOYMENT.md)
