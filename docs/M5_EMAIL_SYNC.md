# M5.1 招聘邮件同步

## 1. 统一处理链路

```text
QQ IMAP / Gmail API / 手动 .eml
        ↓
MailboxMessage(raw RFC822)
        ↓
RecruitmentEmailFilter（关键词/发件人/主题）
        ↓
复用 parse_eml()（M2-R2）
        ↓
ConflictDetectionService（匹配申请 + 冲突分类）
        ↓
RecruitmentEventCandidate（待确认）
        ↓
用户确认 → ApplicationService.add_event()
        ↓
Dashboard / Applications / Calendar 刷新
```

三种来源共用同一解析、匹配与事件生成逻辑，不为各邮箱维护独立状态机。

## 2. 增量游标

| Provider | 游标 |
|---|---|
| QQ IMAP | `imap_uidvalidity` + `imap_last_uid`（`UID n:*` 增量） |
| Gmail | `gmail_history_id`（预留；当前按 `newer_than:30d` + 关键词查询） |

- 首次同步限制 `MAILBOX_SYNC_LOOKBACK_DAYS=30`、`MAILBOX_SYNC_MAX_MESSAGES=200`。
- `UIDVALIDITY` 变化会重建游标（当前记录，未做显式差异告警）。
- 同步失败不跳过未处理邮件（下次仍按游标重试）。

## 3. 招聘邮件过滤

规则（`RecruitmentEmailFilter`）：

1. 解析出 company/title/status 任一 → 视为招聘邮件；
2. 否则正文/主题/发件人命中关键词（招聘、面试、笔试、测评、offer、简历、投递、interview、assessment 等）。

只在必要时读取正文；不下载附件；不自动访问邮件中的链接。

## 4. 候选生成

- 幂等键：`user_id + provider + message_reference`（message_reference = provider:message_id:sha256(raw)）。
- 重复同步 → `duplicate_count++`，不重复创建候选。
- 低置信度 / 无法匹配申请 → `review_status=conflict` 或 `missing_information`。
- 高置信度仅代表关联更可信，**不代表自动获得修改权限**。

## 5. 确认机制

`POST /recruitment-email-candidates/{id}/confirm`

- 必须选择申请记录（默认取自动匹配结果）。
- `keep_current=true` → 只标记确认，不写入事件。
- 否则写入 `ApplicationEvent`，`source_type=email_import`，
  `verification_status=email_confirmed`，`source_reference=mailbox:{message_reference}`（幂等）。
- 丢弃：`POST .../discard` → `review_status=discarded`。

## 6. 同步结果

`MailboxSyncRun` 记录 scanned / candidate / duplicate / error / status / 错误摘要。
`GET /mailboxes/{id}/sync-runs` 返回最近 20 次。

## 7. 前端

- `/settings/email`：绑定 QQ、Gmail 授权、测试连接、立即同步、暂停/开启、解绑、同步记录。
- `/applications`：`EmailSyncCenter` 展示待确认/冲突候选，支持选择申请、状态、确认、仅保留当前、忽略。

## 8. 未完成

- Gmail `historyId` 增量尚未接入 `users.history.list`。
- 邮件附件、正文链接不处理（有意为之）。
- 真实 QQ/Gmail 邮箱未完成端到端同步验收。

---

# M5.2 真实同步验收与过滤器修复（2026-10-23）

## 1. 真实同步结果

两个邮箱均为真实绑定（QQ `1498…@qq.com`、Gmail `lvxu…@gmail.com`），真实 IMAP / Gmail API 读取：

| 轮次 | 邮箱 | status | scanned | candidate | duplicate | 耗时 |
|---|---|---|---:|---:|---:|---:|
| 首次 | QQ | success | 36 | 19（旧规则，含噪音） | 0 | 7.1s |
| 增量 | QQ | success | 0 | 0 | 0 | 0.66s |
| 首次 | Gmail | success | 3 | 3（旧规则，含噪音） | 0 | 3.6s |
| 重复 | Gmail | success | 3 | 0 | 3 | 3.6s |
| 新规则 | Gmail | success | 3 | **0** | 0 | 2.95s |

- 幂等：重复同步 `duplicate=3`，不重复创建候选。
- 只读：`readonly` + `BODY.PEEK`，未修改任何邮件已读状态。
- 未删除、未修改用户真实邮件。

## 2. 发现的缺陷（已修复）

**旧规则把非招聘邮件当成招聘通知**：

| 样本 | 旧结果 | 原因 |
|---|---|---|
| Apple 营销（"special offer"） | 误判 `offer` | `OFFER` 关键词含裸 `"offer"` |
| Steam 充值 / GitHub CI / QQ 安全提醒 | 生成候选 | 关键词含 `申请`/`application` 等泛词 |
| NVIDIA 营销 | 误判公司 `360` | 公司识别全文子串匹配 |

## 3. 修复内容

1. **状态规则收紧**：`OFFER` 只匹配 `录用通知 / 录用offer / offer letter / 发放offer / 已录用 / 录取通知 / 恭喜您被录用 / 正式录用`。
2. **公司识别**：新增 `_company_from_sender()`，优先从发件人域名（`hr@bytedance.com` → 字节跳动）解析；正文匹配要求出现招聘语境词。
3. **过滤器收紧**：
   - 只保留强招聘信号（招聘/面试/笔试/测评/简历/投递/校招/实习/录用…）
   - 命中 ≥2 个信号，或 ≥1 个信号 + 解析出公司/岗位/状态才保留
   - 明确营销/通知类发件人（`news@`、`notifications@`、`steampowered.com`、`accounts.tencent.com`）需 ≥2 信号

## 4. 验证

| 样本 | 结果 |
|---|---|
| `hr@bytedance.com` 面试邀请 | keep=True, company=字节跳动, status=interview |
| `hr@meituan.com` 录用通知 | keep=True, company=美团, status=offer |
| QQ 安全中心 | keep=False |
| Apple 营销 | keep=False |

历史 39 条噪音候选已按新规则标记 `discarded`（保留记录，未删除）。

## 5. Gmail historyId 增量

| 轮次 | scanned | historyId |
|---|---:|---|
| 1（首次） | 3（list + profile 初始化） | SET |
| 2 | **0**（history.list 增量） | SET |
| 3 | **0** | SET |
| historyId 失效（置 1） | 3（受控重扫 + 重新初始化） | SET |

- `users.getProfile` 拿 `historyId`；`users.history.list(startHistoryId, messageAdded)`
- 404 → 有界重扫 + 重新初始化
- 增量去重依赖 `message_reference` 幂等键

## 6. 未完成

- 用户邮箱中暂无真实招聘邮件，**真实招聘邮件的端到端闭环**（确认→事件→看板）仅在自动化测试与样本解析中验证。
- QQ `UIDVALIDITY` 变化仅记录，未做显式告警。

---

# M5.3 QQ UIDVALIDITY 代际处理（2026-10-23）

## 1. 此前的缺陷

`QQIMAPConnector._uidvalidity()` 用 `client.uid("search", None, "ALL")` 然后读 `client.response("UIDVALIDITY")`。`UID SEARCH` 返回的是邮件 id，不是邮箱代际，因此该函数**恒返回 None**——游标里的 `imap_uidvalidity` 一直是空的，代际变化根本无法检测。

## 2. 修复

```python
values = client.untagged_responses.get("UIDVALIDITY")   # SELECT 后的未标记响应
```

同步时把游标里的旧代际传入 `list_messages(..., expected_uidvalidity=...)`：

| 情况 | 行为 |
|---|---|
| 代际未变 | 按 `UID last_uid+1:*` 增量 |
| 代际变化 | **不复用旧 last_uid**，回退到 `SINCE lookback_days` 有界重扫 |
| 首次同步（无游标） | 同样走有界重扫 |

重扫时 `imap_last_uid` 取新代际下的最大 UID；`MailboxSyncRun.status` 置为 `partial`，`error_summary` 记录：

> IMAP UIDVALIDITY 已变化，已按新的代际全量重扫；扫描窗口外的历史邮件可能未被覆盖，请按需补充同步

## 3. 幂等

去重仍依赖 `message_reference = provider:message_id:sha256(raw)`，重扫重复邮件只会命中 `duplicate_count`，不产生新候选/事件。

## 4. 验证

`tests/test_imap_uidvalidity.py`（5 项，全部通过）：

- 从 SELECT 响应正确读取代际；
- 无代际时返回 None；
- 代际不变 → UID 增量；
- 代际变化 → 走 SINCE 重扫，且不出现 `UID 501:*`；
- 首次同步 → SINCE。

真实同步复核（QQ）：`cursor uidvalidity=1594275517`，`scanned=0`（增量已到最新），此前该值一直是 `None`。

## 5. 未完成

- 代际变化只写入 `error_summary` + `partial` 状态，**未接入邮件/站内通知**；
- 未做"扫描窗口不完整"的显式用户提示 UI；
- 断电/Worker 中途重启的游标原子性依赖单次 `commit`，未加专门的恢复测试。
