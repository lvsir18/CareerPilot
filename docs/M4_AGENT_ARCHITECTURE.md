# M4 LangGraph 多 Agent 架构

> 日期：2026-10-22
> 状态：核心架构已实现并可测试；**真实 LLM 端到端验证未通过（未配置 LLM key）**

## 1. 总体架构

```text
FastAPI (auth/CSRF/user)
    → AgentService
    → Supervisor StateGraph (StateGraph + PostgreSQL Checkpointer)
        ├── understand  (LLM structured output → Intent/constraints)
        ├── execute     (按 required_agents 调度专业 Agent 子图)
        └── aggregate   (LLM 汇总 → final_answer)
    → 专业 Agent（langchain.agents.create_agent + 受限工具）
        ├── job_search   → JobDiscoveryService / JobLeadService
        ├── job_match    → RecommendationService / MatchingService
        ├── profile      → ProfileService（只读）
        └── progress     → ApplicationService（只读）
    → Tool Layer（按用户 RuntimeContext 构建，user_id 闭包注入）
    → PostgreSQL（业务数据）+ Redis（缓存）+ LangGraph Checkpoint
```

## 2. 模块

```text
backend/app/agents/
├── llm.py          # 统一 LLM Gateway（ChatOpenAI，OpenAI-compatible）
├── runtime.py      # RuntimeContext + CareerAgentState + 状态机
├── tools.py        # 9 个业务工具（job/match/profile/progress）
├── agents.py       # 四个专业 Agent（create_agent）
├── supervisor.py   # Supervisor StateGraph
├── checkpoint.py   # PostgreSQL PostgresSaver（context manager）
└── service.py      # AgentService（run/resume/history）
```

## 3. LLM Gateway

- `LLM_PROVIDER=openai_compatible`，`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`
- `build_chat_model()` 返回 `ChatOpenAI`（tool calling + structured output）
- 无 key 时 `LLMNotConfiguredError`，Agent API 返回 503，不降级为伪 Agent
- key 只存在服务端，不进前端/日志/Trace

## 4. 工具层与权限

- 工具按用户 `RuntimeContext` 构建，`user_id` 由 FastAPI 认证注入、闭包捕获
- LLM 无法通过参数伪造 user_id
- 只暴露受限业务工具，无 SQL/HTTP/文件/命令执行
- 9 个工具均有 Pydantic `args_schema` + 参数边界

## 5. State 与持久化

- `CareerAgentState`（TypedDict）：messages/intent/constraints/plan/agent_results/status/errors/final_answer
- 状态机：created / running / waiting_for_user / completed / partial / failed / cancelled
- PostgreSQL `PostgresSaver`（`checkpoint_saver` context manager，启动时 setup 建表）
- `thread_id` 绑定 user（`{user_id}:{thread_id}`），Checkpoint 隔离
- 业务会话元数据：`agent_threads` 表（标题/状态），消息历史从 checkpoint 读取

## 6. Human-in-the-Loop

- 完整匹配要求画像已确认；未确认时 `execute` 节点调用 `interrupt()`
- 返回 `WAITING_FOR_USER`，用户确认后 `Command(resume=True)` 恢复
- 恢复时重新读取最新 Profile Version

## 7. 已知限制

- 真实 LLM 未配置，Agent 实际执行无法验收；
- SSE 流式事件未实现（run 为同步执行）；
- 运行预算参数已配置，但图步数/工具调用上限未在首版严格绑定到运行时；
- 幂等 request_id 未实现；
- 取消为状态标记，未中断正在同步执行的图。
