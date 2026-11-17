# M5.1 邮箱连接（QQ IMAP / Gmail OAuth）

> 日期：2026-10-22
> 状态：QQ IMAP 与 Gmail OAuth **代码已实现并通过 mock 测试**；真实凭据未配置，真实绑定验收**未完成**。

## 1. 数据模型

| 表 | 用途 |
|---|---|
| `mailbox_connections` | user_id / provider / email_address / status / `encrypted_secret` / sync_enabled / last_sync_at / last_success_at / last_error |
| `mailbox_sync_cursors` | folder / `gmail_history_id` / `imap_uidvalidity` / `imap_last_uid` |
| `mailbox_sync_runs` | status / scanned / candidate / duplicate / error 统计 |
| `recruitment_event_candidates` | 待确认招聘事件（唯一约束 user_id + provider + message_reference） |

迁移：`5d6e7f8a9b0c_m51_mailboxes.py`。

## 2. 凭据安全

- 使用 **Fernet 认证加密**（`cryptography`）。
- 密钥来自环境变量 `MAILBOX_SECRET_KEY`，**不写进 Git**；`.env` 已被 `.gitignore` 忽略。
- 未配置密钥时：
  - 保存凭据 → `503 MAILBOX_SECRET_UNAVAILABLE`；
  - Gmail OAuth → 明确返回“未配置”。
- 数据库只存密文；API 不返回凭据；日志不输出明文。
- 解绑时清空 `encrypted_secret` 并删除连接。
- 局限：本地为应用层加密，尚未接入 Vault/KMS；生产应使用独立密钥管理。

## 3. QQ 邮箱（IMAP）

- 固定 `imap.qq.com:993`，**前端不能自定义 host/port**，避免 SSRF。
- 使用授权码（非登录密码）登录。
- `select(readonly=True)` + `BODY.PEEK[]` 读取，不修改已读状态。
- 只读，不使用 SMTP。
- 测试连接：`POST /mailboxes/{id}/test`。
- 授权码失效：返回 `MAILBOX_AUTH_FAILED`，连接标记 `error`，提示重新绑定。

**真实验证**：使用假授权码调用，实际连接到 `imap.qq.com:993` 并返回 `422 MAILBOX_AUTH_FAILED`，证明真实 IMAP 链路工作（非 mock）。**未使用真实 QQ 授权码完成绑定**。

## 4. Gmail（OAuth 2.0）

- Authorization Code + **PKCE(S256)** + `state`（Fernet 加密，绑定 user_id 防串号）。
- Scope 仅 `gmail.readonly`，不申请 modify/send。
- 使用官方 REST API：`messages.list` / `messages.get(format=raw)` / `profile`。
- Refresh Token 加密存储；Access Token 每次刷新。
- 未配置 `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI` 时：
  `GET /mailboxes/gmail/authorize` → `configured=false`，**不提供伪授权按钮**。

**真实验证**：当前返回 `configured=false`，未执行真实 Google 授权。

## 5. API

```text
GET    /api/v1/mailboxes
POST   /api/v1/mailboxes/qq/connect
GET    /api/v1/mailboxes/gmail/authorize
GET    /api/v1/mailboxes/gmail/callback
POST   /api/v1/mailboxes/{id}/test
POST   /api/v1/mailboxes/{id}/sync
PATCH  /api/v1/mailboxes/{id}
DELETE /api/v1/mailboxes/{id}
GET    /api/v1/mailboxes/{id}/sync-runs
```

全部要求登录 + CSRF；查询与变更均按 `user_id` 隔离。

## 6. 定时同步

- Celery task：`careerpilot.sync_mailbox` / `careerpilot.sync_enabled_mailboxes`。
- Beat 默认 15 分钟（`MAILBOX_SYNC_INTERVAL_MINUTES`）。
- Redis 锁 `cp:mailbox:lock:{connection_id}`（280s）防止并发重复同步。
- 用户可关闭自动同步（`sync_enabled=false`），手动同步仍可用。

## 7. 未完成

- 真实 QQ 授权码绑定与真实邮件同步未验收。
- Google OAuth 真实授权未验收（无 Client 配置）。
- 未实现远端 Token 撤销（解绑仅删除本地凭据）。
