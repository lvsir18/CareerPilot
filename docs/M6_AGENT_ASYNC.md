# M6-A Agent 异步执行

> 日期：2026-10-23

## 1. 问题

M4/M5 的 `POST /agent/threads/{id}/runs` 在图内**同步执行** LangGraph，单次约 40–50 秒：
- FastAPI 请求被长时间占用；
- 客户端默认 6s 超时 → "无法连接 API 服务"（M5.3 曾用 180s 超时绕过）；
- 无法取消、无法可靠恢复、SSE 无从谈起。

## 2. 架构

```
POST /api/v1/agent/runs            (202, 立即返回)
        │  幂等 request_id → DB 唯一约束
        v
agent_runs(row, status=queued) + agent_run_events(run.queued)
        │
        v  celery: careerpilot.run_agent_run
Celery Worker
        │  claim(): queued → running（并发闸门）
        v
AgentService.run(..., on_event=emit)
        │  emit → 独立 DB 连接写事件（不阻塞图执行）
        v
agent_runs(status=completed|partial|failed|waiting_for_user, result=...)
```

## 3. 数据模型（新增，迁移 `6e7f8a9b0c1d`）

| 表 | 关键字段 |
|---|---|
| `agent_runs` | user_id, thread_id, request_id, status, input_payload, result, error_code, error_summary, created_at, started_at, finished_at, cancel_requested_at, attempt_count |
| `agent_run_events` | run_id, sequence, event_type, safe_payload, created_at |

状态：`queued / running / waiting_for_user / completed / partial / failed / cancelled / timed_out`

**状态不可回退**：`set_status()` 对已处于终态的 run 拒绝写回 `queued/running/waiting_for_user`，
迟到的 Worker 结果不能复活已完成的任务。

## 4. 幂等 request_id

- DB 唯一约束 `(user_id, request_id)`；
- 同 request_id + 同内容 → 返回已有 run（不重复执行）；
- 同 request_id + 不同内容 → `409 AGENT_REQUEST_CONFLICT`；
- 不同用户可用相同 request_id（互不干扰）；
- 不依赖 Redis 锁，用 PostgreSQL 约束 + 事务兜底并发。

## 5. 派发一致性

1. Run 先 `flush` 持久化并写 `run.queued`；
2. 再 `run_agent_run.delay(run_id)`；
3. 派发失败时 API **不报错**（`contextlib.suppress`），run 留在 `queued`，可由重试/补偿拾起，且 `claim()` 保证不会重复执行。

## 6. 取消与超时（协作式）

- `POST /agent/runs/{id}/cancel` 写 `cancel_requested_at` + `run.cancel_requested` 事件；
- Worker 在图执行完成后检查该标记，若已请求则置 `cancelled`；
- `soft_time_limit=240s / time_limit=300s`；
- **不杀 Worker**，不影响邮箱同步任务；
- 取消是协作式的：正在进行的工具调用会先结束或超时，不承诺瞬时终止。
