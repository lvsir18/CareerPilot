# M6-F 个人版部署

> 日期：2026-10-23

## 1. 服务

沿用现有 Compose：`web / api / postgres / redis / worker / scheduler`。
Agent 长任务与邮箱同步**共用同一个 Celery Worker**（未观察到实际资源竞争，故未拆分队列）。

## 2. 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/start.sh` | 检查 `.env` 关键变量 → `docker compose up -d --wait` → 打印入口 |
| `scripts/stop.sh` | `docker compose stop`（**不删 volume**） |
| `scripts/status.sh` | 容器状态 + 邮箱最近同步 + 同步运行记录 + Agent Run 状态分布 |
| `scripts/backup.sh` | 一致性备份（见 `M6_BACKUP_RECOVERY.md`） |
| `scripts/restore.sh` | 隔离库恢复（默认不覆盖真实库） |

## 3. 访问边界

- 默认 `http://localhost:3000` / API `http://localhost:8000`；
- 数据库、Redis **不对外暴露端口**到局域网/公网（仅 Compose 内网）；
- 如需远程访问（Tailscale 等），须另行评估网络绑定与认证，**不要**把本机方案视为公网安全。

## 4. 环境

- `.env.example` 已包含 M4–M6 全部变量；
- `MAILBOX_SECRET_KEY` 必须自行生成并妥善备份（与数据库备份分开保管）；
- Docker `npm ci` 使用 `registry.npmmirror.com` + BuildKit 缓存（M5.3 修复，保持可复现）。

## 5. 健康检查

```bash
./scripts/status.sh
curl -s localhost:8000/readyz
docker compose ps
```

## 6. 未做

- 未做公网部署 / 域名 / HTTPS（明确排除）；
- 未配置 logrotate；
- 未接入监控告警平台。
