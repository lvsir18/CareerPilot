# M5.1 邮件状态冲突检测

## 1. 分类

`ConflictDetectionService.detect()` 输出 `conflict_kind`：

| 值 | 含义 | 处理 |
|---|---|---|
| `none` | 无冲突 | 进入待确认 |
| `duplicate` | 已存在同阶段同时间事件 | 跳过，不重复写入 |
| `out_of_order` | 邮件事件时间早于当前状态确认时间 | 不覆盖当前状态，可补历史 |
| `status_conflict` | 已结束状态互相矛盾（offer/rejected/withdrawn/closed） | 必须人工确认 |
| `ambiguous_match` | 无法可靠匹配到申请 | 必须人工选择申请 |
| `missing_information` | 邮件没有明确阶段 | 不自动推断 |

## 2. 规则

```python
if parsed.status is None: return "missing_information"
if application_id is None: return "ambiguous_match"
if 存在同 status + 同 event_time 事件: return "duplicate"
if parsed.event_time < application.last_confirmed_at and 状态不同:
    return "out_of_order"
if parsed.status 与 application.status 均属于已结束状态且不同:
    return "status_conflict"
return "none"
```

关键原则：

- 邮件发送时间 ≠ 面试开始时间；`scheduled_event_time` 与 `event_time` 分开存储。
- 旧事件允许补充到时间线，但不自动覆盖当前状态。
- 状态不明确时不自动推断。
- 所有写入都追加 `ApplicationEvent`，不覆盖历史。

## 3. 前端

`EmailSyncCenter` 在 `/applications` 展示：

- 当前申请状态（通过申请选择器体现）
- 邮件解析状态与事件时间
- 冲突类型与原因
- 置信度与证据摘要

可选操作：

- **确认更新**（写入事件）
- **仅保留当前**（`keep_current=true`，只标记确认）
- **忽略**（discard）

## 4. 未完成

- 冲突弹窗尚未做成独立模态框（当前内联在候选行）。
- 未实现“多封邮件互相矛盾”的跨邮件聚合检测。
- 未实现“一封邮件匹配多个申请”的显式多选引导（当前由用户手动选择申请）。
