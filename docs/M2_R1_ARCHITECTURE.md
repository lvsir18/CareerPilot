> 当前实现备注：搜索 API 已收敛为 Tavily；本文中 Brave/Bing/Google 等为 M2-R1 历史设计，相关接口已删除。

# M2-R1 架构与实施记录

> 版本：2026-10-21  
> 范围：官方招聘站点限定发现 + JobLead / SourceEvidence + 手动候选导入 + 前端最小闭环  
> 不在范围：自动投递、自动填写表单、登录后批量采集、Cookie 代管、M3 匹配、M4 Agent

## 1. 与现有代码的差异审计

复用：

- `Job` / `JobSource` / `RawJob` / `SyncRun` 与现有 M1/M2 迁移；
- `JobService`、`JobRepository`、`JobIngestion`（`upsert_raw_job`）；
- 百度 `BaiduPublicConnector`（只读公开详情页）；
- M1 认证、用户隔离、CSRF、限流；
- 现有前端 App Shell、岗位卡片、导入页。

新增：

- `job_leads`：候选链接，不代表完整 Job；
- `source_evidence`：搜索/官方页面/用户粘贴留痕；
- `JobDiscoveryService`：联邦发现；
- 可替换搜索 provider（Brave / Bing / Google CSE）+ 百度官方公开列表 provider；
- `JobLeadService`：候选 upsert、私有导入、官方核验；
- `GET /jobs/discover`、`/job-leads/*`；
- `/discover` 前端页面。

明确不做：

- 不把搜索结果直接写成 `Job`；
- 不把搜索摘要当完整 JD；
- 不实现站内投递；
- 不在未授权站点执行登录/批量访问。

## 2. 数据模型

### JobLead

| 字段 | 说明 |
|---|---|
| `owner_user_id` | NULL=公开发现；非空=用户私有导入 |
| `company_id` / `title` / `official_url` | 官方域名标准化后的候选 |
| `summary` | 搜索摘要或用户粘贴 JD（私有） |
| `source_method` | `search_discovery` / `manual_import` |
| `verification_status` | `search_snippet_only` / `user_provided` / `verified_official` / `stale` |
| `published_date` | DATE，仅官网明确日期；缺失为 NULL |
| `first_seen_at` / `last_seen_at` / `last_verified_at` | 三种不同时间 |
| `job_id` | 核验成功后关联的已核验 Job |
| `source_payload_hash` | 判断搜索摘要是否变化 |
| `dedupe_key` | 公开/私有范围 + 规范化 URL 的唯一键 |

### SourceEvidence

- `job_id` / `lead_id` 至少一个；
- `evidence_kind`：`search_result`、`official_page`、`user_paste`、`verification_attempt`；
- `verification_method`：`search_provider`、`official_list_page`、`public_page_parse`、`user_confirmed`、`none`；
- `source_url`、`captured_at`、`content_hash`。

## 3. 发现流程

```text
query/company/city/type
        ↓
SearchService
  ├─ licensed provider (Brave/Bing/Google CSE, key 可选)
  └─ BaiduOfficialListProvider (公开列表页，单页)
        ↓
URL allowlist + canonicalization + query/city/type 过滤 + 去重
        ↓
JobLead upsert（公开候选）
        ↓
用户点击“尝试核验”
        ↓
BaiduPublicConnector 单详情页解析
        ↓
upsert_raw_job → 已核验 Job + SourceEvidence
```

### 搜索 provider

- `SEARCH_PROVIDER=none|brave|bing|google`；
- key 只从环境变量读取；
- Brave/Bing/Google 请求固定官方 endpoint，不接收用户 URL；
- 查询自动加 `site:` 限定到经过配置的企业官方招聘域名；
- 结果 URL 必须通过官方域名、https、详情路径校验；
- 支持超时、429 提示、Redis 限流、Redis 缓存、provider 故障降级；
- 未配置 key 时明确标记 `licensed_configured=false`，不使用模拟搜索结果。

### 官方列表 provider

- `baidu_official_list` 只读取 `talent.baidu.com/jobs/list?recruitType=INTERN|GRADUATE` 一页；
- 解析 `window.__INITIAL_DATA__.listData.listDetailData`；
- 返回标题、官方详情 URL、日期、城市、项目类型；
- 不翻页、不批量访问详情；详情由用户点击核验时单独读取；
- 不是 licensed search API，UI 和 API 都标明该区别。

## 4. 权限与可信状态

- 公开搜索 lead 所有登录用户可见；
- 用户手动导入 lead 默认 `owner_user_id=user`，仅本人可见；
- `GET /job-leads`、`GET /job-leads/{id}`、核验均按用户过滤；
- 他人私有 lead 返回 404；
- 用户打开官网链接不改变任何状态；只有显式 `POST /verify` 才改变；
- 搜索摘要 lead 不进入 `Job` 库，不能被 M3 当作完整 JD；
- `verified_official` 才关联完整 Job；`user_provided` 永不自动升级为官方核验。

## 5. API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/jobs/discover` | 返回已有 Job + 公开/本人 lead + 搜索状态 |
| GET | `/api/v1/job-leads` | 候选列表，私有内容过滤 |
| POST | `/api/v1/job-leads/import` | 官方 URL + 可选 JD，私有导入 |
| GET | `/api/v1/job-leads/{id}` | 候选详情 + 来源证据 |
| POST | `/api/v1/job-leads/{id}/verify` | 仅对允许的官方页面核验 |
| GET | `/api/v1/jobs/{id}` | 已核验岗位 + evidence |

所有写接口沿用 M1 CSRF；搜索/核验有 Redis 限流；返回错误时已有库仍可查。

## 6. 实际运行记录

- 时间：2026-10-21
- 查询：`query=实习`, `company=baidu`, `days=7`
- provider：`baidu_official_list`（licensed search API 未配置）
- 发现候选：10 条官方详情链接
- 尝试核验：3 条
- 核验成功：3 条（尝试成功率 100%，占本次候选 30%）
- 未核验：7 条保留为 `search_snippet_only`
- 真实岗位库：3 条 `is_demo=false` 的百度岗位
- 失败：本次 3 次核验均成功；未对失败进行伪造记录

## 7. 已知限制

- 没有 licensed search API key，因此其他公司（字节/腾讯/阿里/美团）本轮仅完成 provider 接口与域名 allowlist，未做真实发现；
- 百度只读列表第一页，不能宣称全量或实时；
- 百度列表存在旧岗位（如 2024 年发布），`days` 只过滤本地发现时间，不代表官网发布时间；
- 未核验 lead 只有标题/摘要，不能用于 M3 高精度匹配；
- 官方详情核验目前只实现百度；
- 搜索结果可能有假域名、非详情页、重复链接，已过滤但仍需持续维护域名/路径规则；
- 缓存/限流依赖 Redis，Redis 故障时限流降级但不阻断已有库查询。
