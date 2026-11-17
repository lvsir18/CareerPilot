# M4 Agent 评测

> 日期：2026-10-22
> 原则：不把 Fixture 通过冒充真实在线执行成功；不伪造 LLM 成功率/路由准确率。

## 1. 已完成（自动化测试）

后端 204 passed、前端 25 passed。M4 相关：

| 测试 | 覆盖 |
|---|---|
| test_agent.py | 工具构建与 Schema、画像工具只读当前用户、LLM 未配置抛错、Supervisor 图编译、线程隔离、run 无 LLM 返回 503 |

关键断言：

- `build_all_tools` 返回 9 个带 `args_schema` 的工具；
- `get_profile_summary` 只返回当前用户（不泄露他人邮箱）；
- 无 LLM 时 `AgentService.run` 抛 `LLMNotConfiguredError`；
- `build_supervisor` 用 `create_agent` 子图 + `MemorySaver` 可编译；
- Agent 线程跨用户 404；run 无 LLM 返回 503。

## 2. 真实 LLM 端到端（已完成核心场景）

配置：`LLM_PROVIDER=openai_compatible` + 阿里云百炼 `deepseek-v4.1-flash-1017`（Tool Calling 可用，`response_format` 不可用故改用 Tool Calling 做结构化意图解析）。

| 场景 | 结果 |
|---|---|
| 任务 A 多公司搜索 | ✅ 真实 Tavily 搜索，1 个完整 JD + 14 个 JobLead 摘要分开标注，明确"发布日期未知" |
| 任务 B 智能匹配 | ✅ profile+job_match 调用 MatchingService，8 条岗位按分排序，展示命中技能/缺口 |
| 任务 F HITL | ✅ 未确认画像 → `waiting_for_user` → 确认画像 → resume 重新读画像并匹配 |

耗时：任务 A ~41s，任务 B ~40s（含真实搜索/匹配/LLM）。

## 3. 30 条任务评测集（未完成）

- 尚未建立 30 条（简单/跨 Agent/多轮/失败冲突）任务集；
- 未统计 Task Success Rate / Tool Call Success Rate / Routing Accuracy / 延迟；
- 未执行 P50/P95 延迟、失败原因分布。

## 4. 已解决的关键工程问题

- Python 3.14 下 LangGraph 1.2.16 + langchain 1.4.7 + langchain-openai 1.7.2 可用；
- `create_react_agent` 已弃用 → 改用 `langchain.agents.create_agent`；
- `PostgresSaver.from_conn_string` 是 context manager → 用 `checkpoint_saver` 包装；
- checkpointer 首次迁移的 `CREATE INDEX CONCURRENTLY` 会阻塞在 `idle in transaction`/并发进程上 → 改为应用启动时 setup 一次，并清理了孤儿连接。

## 5. 结论

M4 的架构骨架、工具层、Supervisor/专业 Agent、Checkpointer、HITL、API 与前端已实现并通过确定性测试；但**真实 LLM 验收与 30 条评测集未完成**，因此不能宣称 M4 全部通过。需补充 LLM key 后完成真实端到端验证与评测。
