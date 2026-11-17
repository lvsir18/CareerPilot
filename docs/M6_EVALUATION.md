# M6 测试与验收

> 日期：2026-10-23
> 全部为本轮**重新执行**的实测结果，未沿用上一阶段基线。

## 1. 测试数量

| 层 | 结果 |
|---|---|
| 后端 | **238 passed** |
| 前端 | **34 passed** |
| Playwright（Agent 卡片，desktop） | **1 passed** |
| Lint（后端 + 前端） | 通过 |
| 本地 `next build` | 通过 |
| Docker `web` 构建 | 通过，镜像已部署 |

新增后端测试：`tests/test_agent_runs.py`（7 项）。

## 2. 分层

### Unit / Integration（稳定可重复，不外依赖）

| 用例 | 覆盖 |
|---|---|
| 幂等创建 | 同 request_id 返回同一 run，库内仅 1 行 |
| request_id 冲突 | 同 id 不同内容 → 409 |
| 跨用户 request_id | 各自独立，且不能互相读取（404） |
| 事件有序/回放 | sequence 单调，`after=` 回放为空 |
| 取消 | `cancel_requested_at` 写入，跨用户 404 |
| 未知 thread | 404 |
| 终态保护 | completed 不被写回 running |

### Browser E2E（Playwright）

- `agent-cards.spec.ts`：真实注册 → /agent → 提交 → 等待 → 卡片渲染 → 导航目标存在。
  本轮在**异步路径**下重跑通过（1.4m），证明改造未破坏结构化卡片。

### External Smoke（可选，需真实外部服务）

- Tavily、QQ IMAP、Gmail API、LLM 均为真实调用；
- 常规测试不依赖第三方站点当天可用；
- 邮箱同步只读，不修改/删除真实邮件。

## 3. 故障恢复测试

| 场景 | 结果 |
|---|---|
| 备份 | ✅ 成功，12MB dump + 密钥（600） |
| 隔离库恢复 | ✅ `users=2 / mailbox_connections=2`，随后 DROP |
| 真实库未受影响 | ✅ `users=1 / mailboxes=2` |
| 终态 Run 不被复活 | ✅ 单测通过 |
| Worker 重复投递 | ✅ `claim()` 闸门（queued→running 仅一次） |
| 取消 | ✅ 协作式标记，跨用户隔离 |

**未执行**（需真实破坏性操作，个人版不做）：
Worker 进程真实 kill、断电、Celery 重复投递的真实演练（仅有代码级闸门与单测）。

## 4. 未完成

- `answer.delta` 流式 token；
- `plan.created` / `tool.started` 真实图内事件；
- 30 条任务评测集；
- Vault/KMS 部署。
