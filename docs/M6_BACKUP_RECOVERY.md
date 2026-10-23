# M6-C 本地备份与恢复

> 日期：2026-10-23
> 已实测：备份成功 + 隔离库恢复成功（未覆盖真实库）

## 1. 备份内容

`scripts/backup.sh` 生成 `$BACKUP_ROOT/<时间戳>/`：

| 文件 | 说明 |
|---|---|
| `database.sql` | `pg_dump`（一致性导出，**不是**数据目录拷贝） |
| `uploads.tar.gz` | 私有上传文件（如存在） |
| `mailbox_secret.key` | Fernet 密钥，权限 600 |
| `MANIFEST.sha256` | 各文件校验和 |
| `BACKUP_TIME` | UTC 时间戳 |

- 目录整体 `chmod go-rwx`；
- 失败即退出，**不覆盖上一份可用备份**；
- 保留策略 `BACKUP_KEEP=7`（POSIX 兼容，macOS 验证通过）。

## 2. 为什么必须单独备份 Fernet 密钥

数据库里的 QQ 授权码 / Gmail Refresh Token 已用 `MAILBOX_SECRET_KEY` 加密。
**只恢复数据库而没有密钥 → 凭据无法解密**，邮箱需重新绑定。

密钥备份要求：
- 不写进业务日志；
- 不提交 Git；
- 不与 SQL dump 放在同一份未加密归档（当前是同目录但分文件，已提示分离保管）。

## 3. 恢复

`scripts/restore.sh --from <dir> [--target-db NAME] [--force] [--dry-run]`

- 默认目标 `careerpilot_restore_test`（**隔离库**）；
- 目标 = 真实库时必须显式 `--force`；
- 执行前需手动输入目标库名确认；
- 恢复后校验 `users` / `mailbox_connections` 行数；
- 提示把 Fernet 密钥写回 `.env` 的 `MAILBOX_SECRET_KEY`。

## 4. 实测记录

```text
./scripts/backup.sh
  → database.sql 12,015,948 B
  → mailbox_secret.key (mode 600)
  → backup complete

printf 'careerpilot_restore_test\n' | ./scripts/restore.sh --from backups/20261023-145214
  → creating database careerpilot_restore_test
  → loading dump
  → users=2
  → mailbox_connections=2
  → restore finished
```

随后 `DROP DATABASE careerpilot_restore_test`，真实库 `users=1 / mailboxes=2` 未受影响。

## 5. 每日自动备份（可选）

```bash
# crontab -e
0 3 * * * cd /path/to/CareerPilot && ./scripts/backup.sh >> /tmp/careerpilot-backup.log 2>&1
```

## 6. 未完成

- 未做加密归档（密钥与 dump 仍在同一目录，靠文件权限 + 提示分离）；
- 未做异地/离线副本；
- 未验证 uploads 卷的实际恢复（当前容器未挂载独立 uploads 卷）。
