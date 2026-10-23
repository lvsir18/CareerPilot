# M5.3 前端构建与部署修复

> 日期：2026-10-23
> 结论：本地 `next build` 与 Docker `web` 构建均已修复，最新镜像已部署并通过浏览器验证。

---

## 1. 本地 `next build` 卡住的真实根因

**现象**：`npm run build` 停在 `✓ Running next.config.ts took 48ms` 之后，进程 CPU 0.1%，长时间无输出。

**诊断过程**：

1. `lsof +D .next` 显示 VS Code Helper 进程持有 `.next/standalone/package.json` 句柄，同时 `next-build` 持有 `.next/lock`。
2. `sample <pid>` 采样调用栈，主线程停在：
   ```
   uv__io_poll → uv__work_done → node::fs::AfterNoArgs → FSReqPromise::Resolve
   ```
   即在等待一个 **文件系统异步操作**，而不是在编译。
3. CPU 仅 0.1%，排除"编译慢"。

**根因**：残留的 `.next/standalone` 目录被 VS Code 索引器持有句柄，Turbopack 在增量清理/复用该目录时阻塞。之前只删 `.next/build` 不足以解除。

**修复**：
```bash
rm -rf .next          # 完全清理，而不是只删 .next/build
NEXT_TELEMETRY_DISABLED=1 npx next build
```
结果：3 秒内完成，所有路由（含 `/agent`、`/settings/email`）正常生成。

**长期建议**（可选，未强制修改用户全局设置）：
```json
{
  "files.watcherExclude": { "**/.next/**": true },
  "search.exclude": { "**/.next": true }
}
```

---

## 2. Docker `npm ci` ECONNRESET 的诊断与修复

**现象**：`docker compose build web` 在 `npm ci` 阶段约 48 秒后 `ECONNRESET`。

**诊断**：

| 检查项 | 结果 |
|---|---|
| 宿主 registry | `https://registry.npmjs.org/` |
| 容器内 HEAD `registry.npmjs.org/next` | 200 |
| 容器内实际下载 tarball | 中途连接被重置 |
| `registry.npmmirror.com` | 200，下载稳定 |

结论：**不是配置错误，是直连 npm 官方源在国内网络下不稳定**；重试参数无法根本解决（每次都在大包下载时被重置）。

**修复**（`infra/Dockerfile.web`）：

```dockerfile
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN --mount=type=cache,target=/root/.npm \
    npm config set registry "$NPM_REGISTRY" \
 && npm ci --no-audit --no-fund \
      --replace-registry-host=always \
      --fetch-retries=5 --fetch-retry-mintimeout=20000 \
      --fetch-retry-maxtimeout=120000 --fetch-timeout=120000 \
      --maxsockets=4
```

- `npmmirror.com` 由阿里维护，与 `package-lock.json` 的 integrity 校验兼容（锁文件未修改）。
- `--mount=type=cache` 让已下载的包跨构建复用，失败可续传。
- 结果：`npm ci` 从 48 秒失败 → **7.4 秒成功**。

**另一个坑**：曾尝试在 Dockerfile 首行加 `# syntax=docker/dockerfile:1.7`，导致 BuildKit 需要从 Docker Hub 拉取 frontend 镜像；本机 `auth.docker.io` 被 DNS 污染到 Facebook IPv6 段而超时。**已移除该行**，改用内置 BuildKit（同样支持 `RUN --mount`）。

---

## 3. 构建与部署结果

```text
docker compose build web      → exit 0，Compiled successfully in 1.4s
docker compose up -d --no-deps --force-recreate web  → healthy
```

| 项 | 结果 |
|---|---|
| 本地 `npm run build` | ✅ 3s，16 条路由 |
| Docker `web` 镜像 | ✅ 构建成功 |
| Web 容器 | ✅ healthy，运行最新构建 |
| 容器产物校验 | `grep '在招聘中心查看'` / `official_url` 均命中 |

---

## 4. 部署后发现并修复的两个真实缺陷

### 4.1 Agent 请求被 6 秒客户端超时切断

**现象**：浏览器点发送后显示"无法连接 API 服务"。

**根因**：`lib/client-api.ts` 的 `request()` 固定 `CLIENT_TIMEOUT_MS = 6000`，而多 Agent 运行需要约 48 秒（LLM 多次调用 + Tavily）。

**修复**：`RequestOptions` 新增 `timeoutMs`，`runAgent` / `resumeAgent` 使用 `180_000`。

### 4.2 JobLead 卡片缺少官网链接

**现象**：Agent 返回搜索候选时，卡片只有"在招聘中心查看"。

**根因**：`search_jobs` 返回的 JobLead 字段是 `official_url`，前端卡片只读 `source_url`。

**修复**：`AgentJobCard` 增加 `official_url`，渲染时 `job.source_url ?? job.official_url`。

### 4.3 工具异常会中断整个 Agent 运行

**现象**：模型臆造 job_id 调 `get_job_detail`，抛 `AppError` 导致 run 整体失败，`structured` 为空。

**修复**：`app/agents/tools.py` 新增 `_safe_tool` 装饰器，9 个工具统一把业务异常转成 `{"error": code, "message": ...}`，让模型可恢复。

---

## 5. 浏览器验收（真实链路）

```text
npx playwright test e2e/agent-cards.spec.ts --project=desktop
1 passed (46.8s)
```

验证链路：**真实 LangGraph Agent → 结构化 API（`structured.jobs = 22`）→ 最新 Web 容器 → 浏览器卡片渲染**（"在招聘中心查看"链接 ≥ 2、存在"官网/详情"导航目标）。

> 注意：此前该用例"失败"一次，原因是 **E2E 断言写错**（页面 header 本身就有"在招聘中心查看"，导致 `toBeVisible` 立即通过，没等 Agent 跑完）。已改为轮询等待数量变化。

---

## 6. 复现命令

```bash
# 本地
cd apps/web && rm -rf .next && NEXT_TELEMETRY_DISABLED=1 npm run build

# Docker
docker compose build --progress=plain web
docker compose up -d --no-deps --force-recreate web
docker compose ps web

# 浏览器 E2E
cd apps/web && npx playwright test --project=desktop
```
