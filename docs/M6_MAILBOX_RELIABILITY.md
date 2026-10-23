# M6-B 邮箱同步可靠性

> 日期：2026-10-23
> 本轮**未重新绑定、未删除**任何已有邮箱连接；`MAILBOX_SECRET_KEY` 未变动。

## 1. 当前状态（实测）

| 项 | 结果 |
|---|---|
| QQ 连接 | ✅ active，`1498…@qq.com` |
| Gmail 连接 | ✅ active，`lvxu…@gmail.com` |
| QQ 增量同步 | ✅ `scanned=0`（无新邮件），0.66s |
| Gmail historyId 增量 | ✅ `scanned=0`，0.9–1.0s |
| 重复同步幂等 | ✅ `duplicate` 计数，不重复生成候选/事件 |
| 自动同步 | 每 15 分钟（可配），可暂停 |

## 2. 已具备的能力（M5.1–M5.3 实现，本轮保留）

- **QQ UIDVALIDITY 代际检测**：从 `untagged_responses["UIDVALIDITY"]` 正确读取（此前恒为 None）；
  代际变化时**不复用旧 `last_uid`**，改为 `SINCE lookback` 有界重扫，
  `status=partial` + `error_summary` 记录"可能漏读，请补充同步"。
- **Gmail historyId 增量**：`users.history.list`，404 → 受控重扫 + 重新初始化。
- **去重**：`message_reference = provider:message_id:sha256(raw)`。
- **并发保护**：Redis 锁 `cp:mailbox:lock:{connection_id}`。
- **申请进度仍需用户确认**：确认前不写 `ApplicationEvent`。

## 3. 本轮补充

- `scripts/status.sh` 输出：邮箱 provider/status/自动同步开关/最近成功时间/最近错误，
  以及最近 5 次同步运行（scanned/candidate/duplicate）。
- 明确区分"邮箱已连接" ≠ "招聘进度已同步"（页面与文档均标注）。

## 4. 已验证 vs 未验证

| 层级 | 内容 | 状态 |
|---|---|---|
| B | 真实邮箱 API 读取与增量同步 | ✅ 通过（QQ/Gmail 均实测） |
| A | Fixture 邮件业务闭环 + 冲突检测 | ✅ 通过（M5.3，13 项） |
| C | 真实企业招聘通知闭环 | ❌ **未通过**（邮箱中无真实招聘邮件） |

> C 级不阻塞个人版使用。真实招聘邮件到达后再做 C 级验收，不会把 A/B 写成 C。

## 5. 未完成

- UIDVALIDITY 变化未接入站内通知/徽标（仅落在 `error_summary` 与 `status.sh`）；
- 未做同步失败重试策略的细粒度配置；
- 未对真实 QQ/Gmail 连接执行解绑/撤销（避免破坏已绑定授权）。
