# AGENTS.md · CareerPilot 开发与维护指南

> 面向接手本仓库的 AI Agent / 开发者。先读本文件，再读 `docs/IMPLEMENTATION_STATUS.md`。
> 最后更新：2026-10-23 ｜ 阶段：M1–M6 完成（个人版）

---

## 1. 项目定位

CareerPilot 是面向国内互联网实习 / 校招的**个人求职工作台**：

- 岗位发现（官方站点限定搜索 + 用户主动核验）、已核验岗位库；
- PDF/DOCX 简历解析 → 可编辑个人画像 → `heuristic_v1` 可解释匹配；
- 申请进度登记、`.eml` 导入、QQ IMAP / Gmail 招聘邮件增量同步；
- LangGraph 多 Agent 工作流（Supervisor + 4 个专业 Agent），**异步执行 + SSE 推送**；
- 本地备份/恢复与个人版部署脚本。

明确不做：自动投递、自动填表、托管招聘平台密码 / Cookie、绕过登录或验证码、伪造岗位数据。

---

## 2. 架构总览

```text
Next.js (apps/web, :3000)
        │  same-origin fetch（Cookie Session + X-CSRF-Token）
        ▼
FastAPI (backend/app, :8000)  ── SQLAlchemy 2 ──▶ PostgreSQL 16 (:5432)
        │                                        ▲
        │ enqueue (.delay)                       │
        ▼                                        │
Redis (:6379) ──▶ Celery worker（Agent/邮箱/来源同步）
             └──▶ Celery beat（定时调度）
```

关键点：

- **分层**：`API → Service → Repository → DB`。API 层不写业务规则，Repository 不写事务策略。
- **用户隔离**：所有用户资源查询必须带认证上下文里的 `user_id`；跨用户资源一律 **404**（不是 403）。
- **写操作**：需要可信 `Origin` + `X-CSRF-Token` 双提交（GET 豁免）。
- **长任务**：一律异步（`agent_runs` / `sync_runs` / `mailbox_sync_runs` 表 + Celery），API 立即返回。

---

## 3. 目录速查

```text
backend/
├── app/
│   ├── api/v1/          # auth / profile / jobs / discovery / leads / saved / applications
│   │                    # resumes / matches / mailboxes / agent / agent_runs / system
│   ├── agents/          # supervisor、专业 agent、tools、runtime、run_service（含状态机）
│   ├── auth/            # Argon2、服务端会话、当前用户依赖
│   ├── connectors/      # Connector Protocol、SafeHttpClient（SSRF 防护）
│   ├── search/          # Tavily provider、官方域名 allowlist
│   ├── mailboxes/       # IMAP / Gmail 客户端、增量游标、加密凭据
│   ├── services/        # 领域逻辑、同步、标准化/去重、匹配、邮件解析
│   ├── repositories/    # ORM 数据访问
│   ├── db/models/       # SQLAlchemy 模型（含 agent_run、mailbox_*）
│   ├── security/        # CSRF、登录限流
│   ├── storage/         # FileStorage 抽象
│   └── workers/         # Celery app、tasks、beat 调度
├── alembic/             # 迁移（head 以 `alembic current` 为准）
└── tests/               # pytest（含 app fixture 构建真实 FastAPI 应用）

apps/web/
├── app/(app)/           # dashboard / jobs / discover / import / resumes / profile
│                        # matches / agent / applications / calendar / saved-jobs / settings/email
├── app/login/           # 登录 / 注册
├── components/          # App Shell、岗位卡片、状态控件
├── lib/                 # typed API client、SSE 跟随、筛选映射
└── tests/               # Vitest + Testing Library

scripts/                 # start.sh / stop.sh / status.sh / backup.sh / restore.sh
docs/                    # M2–M6 设计、评估与状态文档
infra/                   # Dockerfile.api / Dockerfile.web
```

---

## 4. 启动与运行

### 4.1 Docker（推荐，个人版正式运行）

```bash
cp .env.example .env                # 或 make env
# 至少填：SESSION_SECRET、MAILBOX_SECRET_KEY、LLM_API_KEY/LLM_BASE_URL/LLM_MODEL
make dev                            # 构建并启动 6 个服务
make migrate                        # alembic upgrade head
make seed                           # 8 条 is_demo=true 演示岗位（生产拒绝）
./scripts/start.sh                  # 等价的一键启动（含 .env 关键变量校验 + --wait）
./scripts/status.sh                 # 容器 + 邮箱同步 + Agent run 状态分布
./scripts/stop.sh                   # 停止但保留 volume
```

入口：Web `http://localhost:3000`、API 健康 `http://localhost:8000/readyz`。
`make dev` **不会**自动迁移，新环境必须 `dev → migrate → seed`。

### 4.2 本地 venv（改后端时更快）

```bash
docker compose up -d --wait postgres redis
make setup                                  # backend/.venv + npm ci
cd backend && .venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
# 另一个终端
cd apps/web && API_INTERNAL_URL=http://localhost:8000 \
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

本地 venv 需把 `DATABASE_URL` / `REDIS_URL` 的主机名从 `postgres` / `redis` 改成 `localhost`。

---

## 5. 质量门（提交前必须全绿）

```bash
make lint        # ruff check + ruff format --check + eslint + tsc --noEmit
make test        # pytest（需 PostgreSQL）+ vitest
make e2e         # Playwright（需先启动服务）
```

- 后端测试会自动创建 `careerpilot_test`（可用 `TEST_DATABASE_URL` 覆盖）、重置 schema 并跑真实 Alembic 迁移。
- 当前基线（最近一次完整运行）：后端 pytest **286 passed**、前端 Vitest **40 passed**、Playwright agent-cards 通过；用例数会随迭代增加，以实际运行结果为准。
- `ruff format .` 是**格式化**命令，`make lint` 只做检查；改完记得本地格式化再提交。

环境变量是 pydantic Settings 单例，测试里用 `monkeypatch.setattr(settings, ...)`，不要重新 import。

---

## 6. 异步 Agent 机制（M6 核心，改动前必读）

### 6.1 数据模型

- `agent_runs`：`user_id, thread_id, request_id, status, input_payload, result, error_code, error_summary, created_at, started_at, finished_at, cancel_requested_at, attempt_count`
- `agent_run_events`：append-only，`(run_id, sequence)` 唯一，`event_type` + `safe_payload`
- 状态机：`queued → running → completed | partial | failed | cancelled | timed_out`，另有 `waiting_for_user`（HITL）

### 6.2 三条不可破坏的规则

1. **幂等**：`(user_id, request_id)` 唯一约束。同 request_id 同内容 → 返回已有 run；同 request_id 不同内容 → **409**。不依赖 Redis。
2. **派发一致性**：先 flush 落库 + 写 `run.queued` 事件，再 `.delay()`；派发失败用 `contextlib.suppress` 吞掉，**不返回 500**，run 留在 `queued` 可补偿。
3. **终态保护**：`claim()` 只允许 `queued → running` 一次；终态不可回退，迟到的 Worker 结果不能复活已结束的 run。

### 6.3 SSE 与降级

- `POST /api/v1/agent/runs`（202）→ `GET /agent/runs/{id}/stream`
- 事件行格式 `id: <sequence>`；续传读 `Last-Event-ID` 或 `?lastEventId=`
- 断线/刷新恢复：`GET /agent/runs/{id}/events?after=N` 回放
- 前端 `EventSource.onerror` 自动降级为 `getAgentRun()` 轮询（2s × 120）
- 取消：`POST /agent/runs/{id}/cancel` 只写 `cancel_requested_at`，Worker **协作式**检查后退出
- 超时：Celery `soft_time_limit=240s / time_limit=300s`

> 不要把 SSE 改成 WebSocket，也不要在 API 进程里同步跑图——那会把 40s+ 的延迟重新带回请求线程。

---

## 7. 邮箱同步（M5/M6）

- 凭据用 Fernet 加密（`MAILBOX_SECRET_KEY`），只存密文；**密钥丢失 = 凭据不可解**。
- QQ IMAP：`UIDVALIDITY` 代际检测 + `SINCE` 回看；UID 失效时整代重扫。
- Gmail：`historyId` 增量拉取。
- 去重键：`message_reference = provider:message_id:sha256(raw)`。
- 并发保护：Redis 锁 `cp:mailbox:lock:{connection_id}`，拿不到锁直接跳过本轮。
- 时间纪律：邮件**发送时间不等于面试时间**，只从正文明确语句提取。

---

## 8. 备份与恢复

```bash
./scripts/backup.sh                                   # pg_dump + uploads.tar.gz + mailbox_secret.key + MANIFEST.sha256
./scripts/restore.sh --from backups/<stamp> --dry-run # 预演
./scripts/restore.sh --from backups/<stamp>           # 默认恢复进 careerpilot_restore_test
./scripts/restore.sh --from backups/<stamp> --force   # 覆盖真实库，需手动输入库名
```

- 失败**绝不覆盖**上一份可用备份（写 `*.tmp`，成功后 `mv`）。
- 保留策略 `BACKUP_KEEP=7`。
- `mailbox_secret.key` 必须与 SQL dump **分开**保管；恢复后贴回 `.env`。

---

## 9. 编码约定

- 时间统一 UTC + ISO 8601；不要让 DB 默认值和 Python `datetime.now()` 同时写同一列。
- 统一响应：分页 `{"data": [...], "meta": {page, page_size, total}}`；错误 `{"error": {code, message, details}}`；每个响应带 `X-Request-ID`。
- 日志不记录密码、Cookie、简历正文、`*_API_KEY`、`MAILBOX_SECRET_KEY`、邮箱授权码。
- 新增用户资源接口时：`get_for_user()` + 仓储层强制 `user_id` 过滤 + 写审计事件。
- 新增表必须配 Alembic 迁移；不要手改已应用的迁移。
- 前端新增调用统一走 `apps/web/lib/client-api.ts`；类型定义放 `lib/api.ts`。
- Demo 数据必须 `is_demo=true`，链接在 `demo.example.org`，`DEMO_MODE=false` 时不可见、不可收藏。

---

## 10. 常见坑（踩过的）

| 现象 | 原因 / 处理 |
|---|---|
| `created_at` 为 NULL 或被应用层覆盖 | 模型重复声明了 `created_at`，覆盖了 `TimestampMixin` 的 `server_default`；删掉重复列 |
| 构造 `AgentRunEvent` 报 `TypeError: missing created_at` | 事件表需要**显式** `created_at` 列，别只依赖 mixin |
| 幂等测试插入多条 run | 断言 `db_session.query(AgentRun).count() == 1`；注意 fixture 用 `_build_app(settings, session_factory)` |
| macOS 上 `head -n -7` 报错 | 用 `tail -n +$((KEEP+1))` 做保留策略 |
| SSE 在反向代理后不实时 | 需要关闭代理缓冲（`X-Accel-Buffering: no` / nginx `proxy_buffering off`） |
| Cookie 在 http 下丢失 | `APP_ENV=production` 会自动 `Secure`，本地保持 `development` |
| 前端 lint 失败因未用导入 | 改完 SSE 代码记得清 `getAgentRunEvents` 这类残留导入 |
| 容器内连不上 DB | Compose 内主机名是 `postgres`/`redis`；宿主机本地跑才用 `localhost` |

---

## 11. 禁止事项

- 不实现/不代理自动投递、自动填表、登录态批量采集、验证码绕过。
- 不把 Token / 授权码 / 密钥拼进 URL、写进日志或提交进 Git。
- 不把 `.env`、`backend/uploads/`、`backups/`、`*.key` 提交到仓库。
- 不删除 `.codebuddy/` 目录（项目元数据，不是缓存）。
- 不在终态 run 上写入结果；不改已应用的 Alembic 迁移；不用 `docker compose down -v` 清理“临时数据”（会删数据卷）。

---

## 12. 文档索引

- 使用者手册：`docs/USER_GUIDE.md`
- 状态总览：`docs/IMPLEMENTATION_STATUS.md`
- 搜索与核验：`docs/M2_CHINA_JOB_SOURCES.md`、`docs/M2_R3_2_JD_VERIFICATION.md`、`docs/M2_R3_SEARCH_EVALUATION.md`
- 画像与匹配：`docs/M3_ARCHITECTURE.md`、`docs/M3_MATCHING_DESIGN.md`、`docs/M3_EVALUATION.md`
- Agent：`docs/M4_AGENT_ARCHITECTURE.md`、`docs/M4_AGENT_WORKFLOWS.md`、`docs/M4_EVALUATION.md`
- 前端与邮件：`docs/M5_FRONTEND_ARCHITECTURE.md`、`docs/M5_USER_FLOWS.md`、`docs/M5_EMAIL_SYNC.md`、`docs/M5_SECURITY_REVIEW.md`
- 异步与运维：`docs/M6_AGENT_ASYNC.md`、`docs/M6_SSE_AND_IDEMPOTENCY.md`、`docs/M6_BACKUP_RECOVERY.md`、`docs/M6_PERFORMANCE.md`、`docs/M6_PERSONAL_DEPLOYMENT.md`、`docs/M6_EVALUATION.md`
