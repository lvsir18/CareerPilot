# M6-D 性能与成本基线

> 日期：2026-10-23
> 本地 Docker（Mac），真实数据库，无外部网络依赖的接口单独标注。

## 1. API 延迟（本地库，5 次采样）

| 接口 | p50 | min | max |
|---|---:|---:|---:|
| `GET /dashboard/summary` | 6.9ms | 5.6ms | 14.3ms |
| `GET /applications` | 3.7ms | 3.7ms | 16.3ms |
| `GET /jobs?page_size=20` | 5.7ms | 4.7ms | 7.0ms |
| `GET /matches/recommendations` | 9.5ms | 9.2ms | 32.8ms |
| `POST /agent/runs`（入队） | **23ms** | — | — |

**关键对比**：Agent 提交从同步 40–50s 降到 **23ms**（异步入队）。

## 2. Agent 执行

| 指标 | 实测 |
|---|---|
| Run 入队延迟 | 23ms |
| Run 执行（真实 LLM + Tavily + 百度兜底） | 约 48–84s |
| 每 Run 工具调用 | 3–5 次 |
| LLM 调用次数 | 每专业 Agent 至少 1 次 + 汇总 1 次 |
| SSE 首事件 | 入队后 <1s（`run.queued` 已持久化） |

## 3. Tavily

- 单次 Discover 搜索按企业拆分为多个查询任务，受 `SEARCH_MAX_QUERIES_PER_REQUEST` 限制；
- Redis 缓存命中不消耗 credits；**缓存结果在 UI 标注来源，不伪装成实时搜索**；
- Tavily 不可用 → 降级到本地岗位库并提示。

## 4. 邮箱同步

| 指标 | 实测 |
|---|---|
| QQ 增量同步（无新邮件） | 0.66s |
| Gmail 增量同步（无新邮件） | 0.9–1.0s |
| Gmail 首次/重扫 | 3.0–5.1s |
| 定时检查间隔 | 15 分钟（可配） |

## 5. 已做的优化

1. Agent 请求不再阻塞 FastAPI（本轮最大收益）；
2. 客户端超时从固定 6s 改为可覆盖（Agent 请求 180s）；
3. 邮箱同步用 Redis 锁防并发重复；
4. 匹配结果版本化缓存（`MatchRecord`），画像不变不重算；
5. 事件写入用独立 DB 连接，不阻塞图执行。

## 6. 未做

- 未新增数据库索引（未观察到实际慢查询证据，避免无依据加索引）；
- 未做前端 bundle 分析；
- 未统计 LLM token 成本（服务商未返回 usage）。
