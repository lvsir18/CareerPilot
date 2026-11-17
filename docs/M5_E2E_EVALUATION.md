# M5 验收与端到端评测

> 日期：2026-10-22
> 原则：真实 API + 真实数据库；不把 Fixture 或静态页面冒充完成。

## 1. 自动化测试

| 项 | 结果 |
|---|---|
| 后端测试 | **206 passed**（含 dashboard 2 项） |
| 前端测试 | **25 passed** |
| 后端 lint | 通过 |
| 前端 lint | 0 error / 0 warning |
| Next.js 生产构建 | **成功**（`/dashboard` `/saved-jobs` `/calendar` `/applications/[id]` 等全部生成） |
| 数据库迁移 | head `4c5d6e7f8a9b` |

## 2. 真实 API E2E

使用真实用户 + 真实 verified Job（8 条）+ 真实 Application：

| 验证 | 结果 |
|---|---|
| `GET /dashboard/summary` | saved=1, applied=1, screening=1, interview=1；latest_jobs=6；recent_events=4 |
| 未来 interview 事件 | 正确进入 `upcoming_events`（2026-10-25） |
| 用户隔离 | 用户 B 全部统计为 0 |
| `GET /saved-jobs` | total=1 |
| `GET /applications` | total=3，status ∈ {applied, screening, interview} |
| `GET /applications/{id}` | status=interview，events=2 |
| 状态筛选 `status=interview` | total=1 |
| `.eml` 导入 | 201，status=needs_review，parsed_status=interview |
| 重复 `.eml` 导入 | duplicate=True（幂等） |
| 登录态前端页面 | `/dashboard` `/discover` `/applications` `/calendar` `/saved-jobs` `/matches` `/agent` 均 **200** |

## 3. 未执行

- 真实浏览器自动化（Playwright/Cypress）未接入；使用 HTTP + 登录 Cookie 验证页面渲染。
- 响应式真机测试未执行。
- 岗位搜索的真实 Tavily 调用在 M2-R3 已测；本轮未重复消耗 credits。

## 4. 已知问题

- 邮件导入的“状态冲突自动检测”未实现，依赖人工确认。
- Agent 结果目前是文本，尚未完全卡片化（仅提供跳转入口）。
- Discover 详情使用 `/jobs/[id]` 页面，未实现侧边抽屉。
- 日历仅列表视图，未实现月/周视图。

---

# M5.1 邮箱同步补充评测（2026-10-22）

## 自动化测试

| 项 | 结果 |
|---|---|
| 后端测试 | **212 passed**（新增 `test_mailboxes.py` 6 项） |
| 前端测试 | **25 passed** |
| 后端 lint | 通过 |
| 前端 lint | 通过 |
| Next.js 构建 | 成功（新增 `/settings/email`） |
| 数据库迁移 | head `5d6e7f8a9b0c` |

新增测试覆盖：

- Fernet 凭据加解密往返；未配置密钥报错；
- QQ 连接接口不泄漏授权码；
- 同步生成候选且重复同步幂等；
- 确认候选写入 `ApplicationEvent` 并更新申请状态；
- Gmail 未配置时返回 `configured=false`；
- 邮箱连接跨用户隔离（404 / 空列表）。

## 真实 API 验证（真实 imap.qq.com）

| 验证 | 结果 |
|---|---|
| `GET /mailboxes` | 空列表 |
| `GET /mailboxes/gmail/authorize` | `configured=false` + 明确说明 |
| `POST /mailboxes/qq/connect`（假授权码） | **422 `MAILBOX_AUTH_FAILED`**，真实连接 `imap.qq.com:993` |
| `GET /recruitment-email-candidates` | 空列表 |
| `/settings/email` `/applications` `/calendar` | 登录态均 200 |

## 未完成（必须如实标注）

- **没有真实 QQ 授权码**，未完成真实邮箱绑定与真实邮件同步。
- **没有 Google OAuth Client 配置**，未完成真实 Gmail 授权。
- **Playwright 浏览器 E2E 未接入**，本轮仍是 HTTP + 登录 Cookie 验证页面渲染。
- **响应式未做真机/视口回归**。
- **Agent 结构化卡片未完成**（Part E）。
- 日历已支持月/周/列表，但未做跨时区显示测试。

因此：M5.1 的“真实邮箱连接”验收状态为 **未完成（缺外部凭据）**，其余代码与 mock 测试已完成。


---

# M5.2 验收补充（2026-10-23）

## 1. 真实邮箱同步

| 项 | 结果 |
|---|---|
| QQ IMAP 真实读取 | ✅ scanned=36/23/1（首次多轮），增量后 0 |
| Gmail API 真实读取 | ✅ scanned=3，增量后 0 |
| 幂等 | ✅ 重复同步 duplicate=3，不新增候选 |
| 首次范围限制 | ✅ 30 天 / 200 封 |
| 错误返回 | ✅ 授权码失效返回 `MAILBOX_AUTH_FAILED` |
| 不修改已读 | ✅ `readonly` + `BODY.PEEK` |
| 普通邮件不误判 | ✅ 修复后 Apple/Steam/GitHub/NVIDIA 全部排除 |
| 暂停/解绑 | ✅ `sync_enabled` 控制，删除连接停同步 |

## 2. Gmail 增量

- 首次：`messages.list` + `profile.historyId` 初始化
- 后续：`users.history.list(startHistoryId)`，无新邮件时 scanned=0
- historyId 失效（404）：受控重扫 + 重新初始化
- 去重：`message_reference` 幂等

## 3. Agent 结构化卡片

- 后端：从 `ToolMessage` 收集真实工具 JSON → `structured{ jobs, matches, applications, progress_events }`
- 前端：`/agent` 渲染岗位/匹配/申请卡片，支持跳转 `/jobs/{id}`、`/applications/{id}`、`/discover?q=`
- 不使用正则解析 LLM 文本

## 4. 仍未完成

- 真实招聘邮件端到端闭环（用户邮箱暂无招聘邮件）
## 5. Playwright 真实浏览器 E2E（已执行）

```text
npx playwright test
6 passed (6.8s)
```

| Project | 视口 | 结果 |
|---|---|---|
| desktop | 1440×900 | ✅ |
| tablet | 768×1024 | ✅ |
| mobile | 375×812 | ✅ |

覆盖：真实浏览器注册登录、Dashboard、Discover 筛选 UI、Applications 视图切换入口、
Calendar、/settings/email、岗位详情跳转、三视口无横向溢出（`scrollWidth - clientWidth <= 2`）。

说明：
- 使用系统 Chrome（`channel: "chrome"`），未下载 Playwright Chromium。
- Discover 未触发真实 Tavily 搜索（避免 E2E 依赖外部网络）。
- E2E 注册的测试账号已清理，未影响真实用户数据。

## 6. 前端构建状态（如实说明）

- 本地 `next build` 受 VS Code 腾讯云 Copilot 扩展索引 `.next` 干扰而卡住；
- 容器内 `docker compose build web` 因 `npm ci` 网络中断（ECONNRESET）失败；
- 因此 **M5.2 新增的 Agent 结构化卡片前端尚未进入 web 容器构建**，需重跑一次容器构建后生效。
- 后端改动（过滤器、Gmail 增量、结构化 API）已在 api/worker 容器生效并验证。
- 日历跨时区显示未测试

---

# M5.3 构建部署与回归（2026-10-23）

## 1. 构建修复（详见 `M5_BUILD_AND_DEPLOY.md`）

| 问题 | 根因 | 结果 |
|---|---|---|
| 本地 `next build` 卡住 | 残留 `.next/standalone` 被 VS Code 索引器持有，Turbopack 卡在 fs 操作 | ✅ 完全删除 `.next` 后 3s 构建成功 |
| Docker `npm ci` ECONNRESET | 直连 npmjs 国内不稳 | ✅ 改用 npmmirror + BuildKit cache，7.4s 成功 |
| Docker Hub 拉 frontend 超时 | `# syntax=` 触发拉取，`auth.docker.io` DNS 被污染 | ✅ 移除 syntax 行 |

## 2. 部署缺陷修复

| 缺陷 | 影响 | 修复 |
|---|---|---|
| 客户端 6s 超时 | Agent 48s 运行被判"无法连接 API" | `timeoutMs` 覆盖，Agent 用 180s |
| JobLead 卡片缺官网 | `official_url` 未读 | 前端兼容 `source_url ?? official_url` |
| 工具异常中断 run | 模型臆造 job_id → 整个 run 失败 | `_safe_tool` 装饰器返回结构化错误 |

## 3. Agent 结构化卡片浏览器验收

单独运行：

```text
npx playwright test e2e/agent-cards.spec.ts --project=desktop
1 passed (46.8s)
```

链路证明：真实 LangGraph Agent → `structured.jobs = 22` → 最新 Web 容器 → 浏览器卡片（"在招聘中心查看" ≥ 2，"官网/详情"导航存在）。

## 3.1 完整 Playwright（三视口）

```text
npx playwright test
7 passed, 2 skipped (2.0m)
```

- desktop：agent 卡片 + 核心页面 + 岗位详情
- tablet / mobile：核心页面 + 岗位详情（agent 卡片按设计跳过，避免重复消耗 LLM）
- 中途曾因注册限流（20 次/5 分钟）失败，已确认这是**正确的安全行为**；测试环境临时提高阈值后通过

## 4. 自动化测试

| 项 | 结果 |
|---|---|
| 后端 | **231 passed** |
| 前端 | **34 passed**（含 12 项跨时区） |
| 后端 lint | 通过 |
| 前端 lint | 通过 |
| 本地构建 | ✅ 3s |
| Docker web 构建 | ✅ 1.4s compile |

## 5. 时区覆盖

`tests/format.test.ts` 新增 12 项：Asia/Shanghai、Asia/Singapore、UTC、America/New_York，
含 2026-03-08 DST 开始与 2026-11-01 DST 结束，以及 `20:00Z` 跨日归属验证。

## 6. 未完成

- Gmail 真实撤销未对真实账号执行（避免影响已绑定连接）；
- Vault/KMS 未部署（已抽象 `SecretStore`，见 `M5_SECURITY_REVIEW.md`）；
- UIDVALIDITY 变化未接入通知；
- 完整 9 项 Playwright 串跑受外部 Tavily/百度抓取耗时影响，单测（agent-cards）已通过。
