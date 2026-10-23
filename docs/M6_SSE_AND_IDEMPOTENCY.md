# M6-A SSE、断线恢复与幂等

> 日期：2026-10-23

## 1. 事件存储

事件落 `agent_run_events`（append-only，`(run_id, sequence)` 唯一），
`sequence` 每个 run 单调递增。**不使用 Redis Pub/Sub 作为唯一事件源**。

## 2. SSE 端点

```
GET /api/v1/agent/runs/{run_id}/stream        (text/event-stream)
GET /api/v1/agent/runs/{run_id}/events?after=N (JSON 回放)
```

- 事件名即 `event_type`：`run.queued / run.started / plan.created / agent.started /
  tool.started / tool.completed / agent.completed / answer.delta / approval.required /
  run.completed / run.partial / run.failed / run.cancelled / run.final`
- 每帧带 `id: <sequence>`，客户端可用 `Last-Event-ID`（或 `?lastEventId=`）续传；
- SSE 断开**不影响 Worker**（Worker 只写 DB）；
- 页面刷新后可用 `/events?after=0` 或 GET run 状态完整恢复；
- 终态时推送 `run.final`（含 `status` 与 `result`），客户端据此渲染卡片。

## 3. 认证

- 走现有 Session/Cookie + CSRF（GET 属 SAFE_METHODS，CSRF 自动豁免）；
- `get_for_user()` 校验 `run.user_id == 当前用户`，跨用户 404；
- **不把 token 拼到 URL**，前端用同源 `EventSource`（cookie 随行）。

## 4. 安全payload

只发送可公开的执行元数据与结构化结果：
事件类型、sequence、agent 名、工具名、耗时、最终 structured/final_answer。
**不发送** LLM 私有推理、API Key、邮箱 Token、简历全文、完整日志。

## 5. 幂等与去重

| 场景 | 保证 |
|---|---|
| 重复提交同 request_id | 同一 run，不重复执行 |
| SSE 重连 | `Last-Event-ID` 续传，客户端按 sequence 去重 |
| Worker 重复投递 | `claim()` 只允许 queued→running 一次 |
| 迟到结果 | 终态不可被写回 running |

## 6. 前端降级

`EventSource.onerror` → 自动切换到 `getAgentRun()` 轮询（2s 间隔，最多 120 次）。
SSE 失败不会导致最终结果丢失。

## 7. 实测

```text
POST /api/v1/agent/runs  → 202, 23ms   （原同步路径 40–50s）
幂等重放                → 同一 run_id
事件序列                → run.queued → run.started → agent.started
                          → agent.completed → run.completed
最终状态                → completed，structured.jobs = 10
浏览器                  → 卡片正常渲染（Playwright 1.4m 通过）
```

## 8. 未完成

- `answer.delta` 流式 token 未实现（当前为整段 final_answer）；
- `plan.created` / `tool.started` 事件尚未从图内真实发出（仅 `tool.completed` 从 tool_results 回填）；
- 未做事件保留期限清理（个人版暂不启用）。
