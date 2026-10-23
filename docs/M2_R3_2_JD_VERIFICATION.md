# M2-R3.2 岗位详情获取与核验

> 日期：2026-10-22  
> 范围：Tavily Extract、JD 结构化、单岗位核验、来源证据、网络安全  
> 不包含：批量抓取、自动投递、登录态采集、M3 匹配

## 1. 流程

```text
Tavily Search
  → JobLead（search_snippet_only）
  → URL 来源与 ATS 租户校验
  → 用户主动点击“获取详情并核验”
  → Tavily Extract（单 URL）
  → JD 规则结构化
  → 完整性/来源/页面状态校验
  → upsert 为 Verified Job
  → SourceEvidence(method=tavily_extract)
```

任一步失败都保留原 JobLead，并写入失败证据与 `last_verification_error`。

## 2. Tavily Extract

实现：`backend/app/services/tavily_extract.py`

- endpoint：`https://api.tavily.com/extract`
- 复用 `TAVILY_API_KEY`
- 单次只接收一个 URL
- 默认深度由 `TAVILY_EXTRACT_DEPTH` 控制；默认 `basic`
- 支持 `advanced`，用于动态渲染页面
- 处理 `results`、`failed_results`、429、超时和网络错误
- Redis 缓存 `TAVILY_EXTRACT_CACHE_TTL_SECONDS`，默认 3600 秒
- 每日预算 `TAVILY_EXTRACT_DAILY_BUDGET`
- 按用户分钟限流
- 不默认批量提取
- 不把搜索摘要当作 Extract 正文
- 不执行页面 HTML/脚本；只做文本清理

当前真实核验环境使用 `advanced`，因为多个动态招聘页在 `basic` 下返回 `Failed to fetch url` 或只返回导航内容。`.env.example` 仍使用默认 `basic`。

## 3. JD 结构化

实现：`backend/app/services/jd_parser.py`

可提取字段：

- company（来自已验证来源配置）
- title
- department（仅显式部门标签）
- location（显式地点标签，或可见城市词，来源标记为 `inferred_city`）
- job_type
- responsibilities
- requirements
- skills（仅显式技能章节）
- official_url
- official_job_id（从 URL 解析，不作为猜测字段）
- published_date（仅显式日期标签/日期+发布文本）
- description

字段来源保存在 `raw_payload_json.field_sources`：

- `config`
- `extracted`
- `lead_title`
- `url_derived`
- `inferred_city`
- `missing`

完整性门槛：

- 有明确标题；
- 有岗位职责/任职要求章节；
- 正文长度 ≥ 200；
- 职责/要求内容 ≥ 80 字符；
- 页面未显示“已下架/关闭”；
- URL 是官方或可信 ATS 详情页。

不满足时不会升级为 Job。

## 4. 核验与升级

实现：`backend/app/services/job_lead_service.py`

- 百度继续使用公开详情页解析；
- 非百度官方/ATS 使用 Tavily Extract；
- 成功后生成 `JobSource(source_type=tavily_extract)`；
- `Job.verification_status=verified`；
- `JobLead.verification_status=verified_official`；
- 写入 `SourceEvidence(evidence_kind=official_page, verification_method=tavily_extract)`；
- 失败写入 `verification_attempt`，保留 `JobLead`；
- `JobLead.last_verification_error` / `last_verification_attempt_at` 供前端展示；
- 重复核验已成功岗位返回 409；
- 列表页、招聘首页、无效 URL 在核验前拒绝。

## 5. 实际在线验证

使用真实 Tavily API，advanced Extrac，单岗位触发：

| 企业 | 候选 URL 类型 | 结果 | 原因 |
|---|---|---|---|
| MiniMax | 飞书 ATS 详情 | **成功** | 已生成 Verified Job |
| 美团 | 官方详情 | **成功** | 已生成 Verified Job |
| 小红书 | 官方详情 | **成功** | 已生成 Verified Job |
| 小米 | 官方详情 | **成功** | 已生成 Verified Job |
| 网易 | 官方详情 `/app/detail/index` | **成功** | 已生成 Verified Job |
| 网易 | `/app/job/position?id=69` | **失败** | 项目/列表页，不是职位详情 |
| 哔哩哔哩 | `/campus/positions/29952` | **失败** | 页面显示“职位已下架” |
| MiniMax | 另一个飞书详情 | **失败** | Tavily 返回 `Failed to fetch url` |

DeepSeek 没有稳定的职位详情候选，因此未执行 Extract。

### 统计

| 指标 | 结果 |
|---|---:|
| 用户主动尝试核验 | 8 |
| Tavily Extract 调用 | 7（无效 URL 未调用） |
| Extract 返回正文 | 6 / 7 = **85.7%** |
| JD 通过核验并升级 | **5 / 7 = 71.4%** |
| 实际升级 Verified Job | **5** |
| 失败保留 JobLead | 3（1 个提取失败、1 个已下架、1 个非详情页） |
| 失败证据 | 3 条 |
| 本轮新增 Verified Job | **5** |
| 历史已核验岗位 | 3 |
| 当前已核验总数 | **8** |
| 应用层 Extract credits | **7** |

另有开发阶段的手动 Tavily Extract 验证调用，不计入应用用户触发预算。

## 6. 失败与限制

- `basic` 对飞书、B站、小红书、网易、美团等动态页面经常 `Failed to fetch url`；
- `advanced` 能取得更多正文，但仍不能保证每个页面都有完整 JD；
- B站页面提取成功但显示已下架，因此按规则拒绝升级；
- 网易 `id=69` 是项目列表，不是岗位详情；新规则拒绝；
- ATS 页面可能只返回招聘入口或列表；
- 未实现自动详情批量抓取；
- 未实现 ATS 官方 API 或浏览器插件；
- 不绕过登录、验证码或访问控制；
- 本轮没有对全部 69 个候选执行 Extract，只验证了用户触发样本；同一 ATS 入口的不同详情页面也可能出现提取失败。

## 7. 网络安全

### 已有防护

- 只允许 https（提取/官方核验 URL）和受限 http；
- 精确 hostname allowlist，拒绝伪造域名；
- 拒绝用户凭据、非常规端口；
- DNS 解析结果必须是公网地址；拒绝回环、内网、链路本地、CGNAT、保留地址；
- 每次重定向重新校验 URL；
- 限制重定向次数、响应体大小、超时、重试和最小请求间隔；
- Tavily Extract 只接收已验证官方/ATS URL，不在服务端直接连接任意用户 URL；
- 单 URL 与每日预算限制。

### 明确限制

`SafeHttpClient` 的 DNS 校验与实际 HTTP 连接仍由不同解析步骤完成，**没有实现 IP 固定绑定**。因此不能声称彻底消除了 DNS rebinding。当前通过仅允许百度公开详情页的本地 Fetch、并让其他来源走 Tavily Extract，来缩小直接服务端抓取面。生产环境如需要更强的连接层绑定，需要自定义 httpcore transport 或网络代理。

### 测试

- 伪造域名拒绝；
- 私网/回环/元数据地址拒绝；
- 重定向到私网拒绝；
- DNS 重解析到 loopback 拒绝；
- ATS 租户越界拒绝；
- 列表页拒绝；
- 提取 URL 非可信来源拒绝。

## 8. 数据库

迁移：`e31a2b7c9d10_m2r32_tavily_extract_evidence.py`

- `job_leads.last_verification_error`
- `job_leads.last_verification_attempt_at`
- `source_evidence.verification_method` 允许 `tavily_extract`

`JobSource(source_type=tavily_extract)` 使用现有表，不新增表。

## 9. 测试与构建

```text
make migrate   # 通过
make lint      # 通过
make test      # 后端 164 passed；前端 25 passed
npm run build  # 通过
```

## 10. M3 数据条件

当前具备：

- 8 条 Verified Job（3 条历史百度 + 本轮 5 条）；
- 已保存完整 JD 的岗位可用于 M3 解析/匹配；
- Tavily/ATS 的其余候选仍为 JobLead，不应用于高精度 JD 评分；
- 发布日期未知的岗位不应被当作“最近发布”；
- 申请进度、邮件导入和时间线未受影响。

本轮完成详情获取与核验能力后停止，不自动进入 M3。
