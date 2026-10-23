# M5.3 邮箱凭据安全审查

> 日期：2026-10-23
> 范围：QQ 授权码 / Gmail Refresh Token 的存储、使用、撤销与迁移计划。
> 说明：本轮**未部署** Vault/KMS，也未声称已部署。

---

## 1. 当前实现

| 检查项 | 结果 |
|---|---|
| 密钥来源 | `MAILBOX_SECRET_KEY` 环境变量（`.env`，已被 `.gitignore` 忽略） |
| 加密算法 | Fernet（AES-128-CBC + HMAC-SHA256，认证加密） |
| 存储位置 | `mailbox_connections.encrypted_secret`（密文，无明文列） |
| api / worker / scheduler 密钥一致性 | 三者共用 `docker-compose.yml` 的同一 `MAILBOX_SECRET_KEY`，一致 |
| 镜像是否包含 `.env` | 否，`.dockerignore` 排除 `.env` |
| API 是否返回凭据 | 否，`MailboxRead` 不含 `encrypted_secret` |
| 日志是否输出明文 | 否，代码中无凭据日志；异常只记录错误码与消息 |
| 未配置密钥时行为 | 返回 `503 MAILBOX_SECRET_UNAVAILABLE`，拒绝保存 |

本轮新增抽象：

```python
# app/services/secret_store.py
class SecretStore(Protocol):
    def encrypt(self, payload: dict) -> str: ...
    def decrypt(self, token: str) -> dict: ...

class FernetSecretStore: ...          # 当前实现
def get_secret_store(settings): ...   # 未来在此接入 vault/kms
```

`mailbox_secret.encrypt_secret/decrypt_secret` 保持原签名，内部委托给 `SecretStore`，调用方无需改动。

---

## 2. Gmail Token 远端撤销

`DELETE /api/v1/mailboxes/{id}` 现在会：

1. `sync_enabled = False`，防止后续任务继续使用；
2. 删除本地密文；
3. 对 Gmail 调用 `https://oauth2.googleapis.com/revoke`；
4. 只有 Google 返回 200 才把 `remote_revoked` 置为 `true`。

响应示例：

```json
{
  "provider": "gmail",
  "local_credentials_deleted": true,
  "remote_revoked": true,
  "message": "已在 Google 端撤销授权"
}
```

失败时 `remote_revoked=false`，`message` 明确提示到 Google 账号安全页手动移除，**不会把"删除本地密文"说成"已撤销"**。

---

## 3. QQ 授权码解绑

删除本地密文并停止同步，响应提示：

> 已删除本地加密授权码；请前往 QQ 邮箱设置撤销该客户端授权码

QQ 没有等价的公开撤销 API，因此**不声称服务端已撤销**。

---

## 4. 未验证 / 未实现

| 项 | 状态 |
|---|---|
| 真实 Gmail 解绑并撤销 | ⚠️ 代码已实现，**未对真实账号执行**（避免影响用户已绑定连接） |
| 真实 QQ 解绑 | ⚠️ 未对真实连接执行，避免删除用户授权 |
| Vault/KMS 部署 | ❌ 未部署 |
| 密钥轮换 | ❌ 未实现（多密钥版本 + 重加密） |
| 远端 Token 撤销验证 | ⚠️ 仅代码路径，无真实调用记录 |

---

## 5. Vault / KMS 迁移方案（计划，未执行）

1. **接口**：`get_secret_store()` 按 `SECRET_BACKEND=fernet|vault|kms` 选择实现。
2. **密钥管理**：
   - Vault：AppRole/Kubernetes Auth 获取短期 token，`transit` 引擎加解密；
   - 云 KMS：`Encrypt/Decrypt` API，密钥由 KMS 托管，应用不持有密钥材料。
3. **密钥轮换**：
   - 密文附带 `key_version` 前缀（如 `v1:<token>`）；
   - 新增版本后，读取时按版本解密，写出时用最新版本；
   - 后台任务分批重加密，**不一次性重写全部用户凭据**。
4. **迁移步骤**：
   1. 部署新后端并保持旧 Fernet 可读；
   2. 打开"写新读旧"双读模式；
   3. 逐批重加密，记录进度；
   4. 全部迁移后下线旧密钥；
   5. 保留旧密钥至少一个备份周期以支持回滚。
5. **访问控制**：凭据只在 `EmailSyncService` 内部解密，Agent/LLM 工具层无法读取；审计日志记录"谁在何时解密了哪个连接"，不记录明文。
6. **备份一致性**：数据库备份必须与密钥备份配套，否则密文不可恢复；密钥不得与数据库备份放在同一存储。

---

## 6. 生产部署前必须完成

1. 使用 Vault 或云 KMS 承载密钥，应用不落盘密钥；
2. 完成一次真实密钥轮换演练；
3. 验证备份/恢复能正确解密；
4. 对真实 Gmail 账号执行一次撤销并确认 `remote_revoked=true`；
5. 审计日志接入，确认无明文凭据。
