# M4 Agent 工作流与工具注册

## 1. Supervisor 工作流

```text
START → understand → execute → aggregate → END
```

- `understand`：LLM `with_structured_output(Intent)` 解析意图、约束、required_agents
- `execute`：按 required_agents 顺序调用专业 Agent 子图，结果写 agent_results；画像未确认时 interrupt
- `aggregate`：LLM 汇总 agent_results 生成 final_answer

路由规则（由意图决定 required_agents）：

| 用户意图 | 调度 |
|---|---|
| 搜索岗位 | job_search |
| 哪些岗位适合我 | profile + job_match |
| 最近面试进度 | progress |
| 我的目标城市 | profile |
| 找未申请且匹配的岗位 | job_search + job_match + progress |

## 2. 多 Agent 协作场景

- 场景 A 跨公司搜索：job_search → JobDiscoveryService → Job/JobLead
- 场景 B 智能匹配：profile + job_match → RecommendationService
- 场景 C 进度查询：progress → ApplicationService + timeline
- 场景 D 组合任务：job_search + profile + job_match + progress → 去重汇总

## 3. 工具注册表（9 个）

| Agent | 工具 | 对应 Service |
|---|---|---|
| job_search | search_jobs / get_job_detail / get_job_leads | JobDiscoveryService / JobService / JobLeadService |
| job_match | recommend_jobs / match_job | RecommendationService |
| profile | get_profile_summary | ProfileService |
| progress | list_applications / get_application_timeline / check_job_application_status | ApplicationService |

全部工具：Pydantic 参数 Schema、边界、结构化返回、用户权限注入；不暴露 SQL/HTTP/文件/命令。

## 4. Tool Registry 扩展

当前为原生 Python 工具（按领域函数工厂）。未来可引入统一 ToolRegistry 注册发现与 MCP 工具，但 M4 不引入独立 MCP Server。
