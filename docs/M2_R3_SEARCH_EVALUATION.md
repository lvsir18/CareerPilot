# M2-R3.1 中国互联网招聘来源与 Tavily 评测

> 评测日期：2026-10-21  
> 固定查询集：`backend/tests/fixtures/m2r3_queries.json`（25 条）  
> 运行脚本：`scripts/m2r3_search_evaluation.py`  
> 运行方式：真实 CareerPilot API + PostgreSQL + 真实 Tavily API，不伪造外部调用

## 1. 搜索与来源架构

- Tavily Search API：唯一第三方网页搜索；
- 百度官方公开列表页：官方兜底；
- 官方招聘主域名；
- 经官网证据验证的第三方 ATS 租户；
- `JobLead` 搜索候选与 `Job` 已核验岗位严格分离。

### 1.1 可信 ATS 租户

| 企业 | ATS | 可信租户/路径 | 官网证据 |
|---|---|---|---|
| MiniMax | 飞书招聘 | `vrfi1sk8a0.jobs.feishu.cn/`，仅此租户 | `https://minimax.cn/careers` 链接到该租户 |
| Kimi | Moka | `app.mokahr.com/apply/moonshot/148506` | `https://careers.kimi.com/campus` 链接到该路径 |
| 携程 | Moka | `app.mokahr.com/campus-recruitment/trip/117988` | `https://careers.ctrip.com/` 链接到该路径 |

约束：

- 不把整个 `jobs.feishu.cn` 或 `app.mokahr.com` 当作某企业专属域名；
- 必须同时匹配 host 和租户路径；
- 其他企业的 Moka/飞书租户会被判定为 `unrelated_page`；
- ATS 详情被接受为 `trusted_ats_job_detail`，但仍只是 `JobLead`，不是完整 JD 已核验岗位。

### 1.2 官方域名单

共 19 家企业进入来源目录，根域名均已在线检查并返回 HTTP 200：

- P0：字节跳动、腾讯、阿里巴巴、百度、美团、小红书、哔哩哔哩、得物、DeepSeek、360；
- P1：小米、MiniMax、京东、Kimi、携程、快手、网易、华为、拼多多。

其中：

- 百度支持官方详情页自动核验；
- 其他企业目前只保存搜索候选和官方链接；
- ATS 页面受动态渲染限制，不把搜索摘要升级为完整 JD。

## 2. 固定查询集与真实结果

25 条查询覆盖 19 家企业。最终运行结果：

| 指标 | Tavily | 百度兜底 | 合计 |
|---|---:|---:|---:|
| 唯一候选 | **66** | **3** | **69** |
| 有效官方/可信 ATS 链接 | 66 | 3 | **69 / 69 = 100%** |
| 企业覆盖 | 8 家 | 百度 | **9 家** |
| 官网发布日期可用 | 0 | 3 | **3 / 69 = 4.35%** |
| 搜索发现重复 URL 比例 | — | — | **0%** |
| Tavily 实际请求 | **43** | — | 43 |
| Tavily credits 估算 | **43** | — | 43 |
| 百度公开页面请求 | — | 1 | 1 |
| 冷启动延迟 | avg **4,697 ms** / p95 **8,752 ms** / max **9,604 ms** | — | — |

43 次 Tavily 请求 = 25 条基础查询 + 18 次受限回退查询。

分企业唯一候选：

| 企业 | 数量 |
|---|---:|
| 字节跳动 | 16 |
| 小红书 | 13 |
| 哔哩哔哩 | 11 |
| 美团 | 9 |
| MiniMax | 8 |
| 腾讯 | 6 |
| 百度 | 3 |
| 网易 | 2 |
| 华为 | 1 |

未产生候选的企业包括阿里巴巴、得物、DeepSeek、360、小米、京东、快手、Kimi、携程、拼多多。原因见第 4 节，不生成模拟岗位。

### 2.1 逐条查询

| # | 企业 | 查询 | 命中 |
|---|---|---|---:|
| q01 | 百度 | Agent 实习 | 3 |
| q02 | 字节跳动 | Agent 大模型 实习 | 10 |
| q03 | 腾讯 | 大模型 算法 校招 | 5 |
| q04 | 阿里巴巴 | 搜索算法 校招 | 0 |
| q05 | 美团 | 大模型 实习 | 4 |
| q06 | 小红书 | 大模型 算法 实习 | 7 |
| q07 | 哔哩哔哩 | 推荐算法 实习生 招聘 | 3 |
| q08 | 得物 | 数据分析 实习 | 0 |
| q09 | DeepSeek | 大模型 实习 | 0 |
| q10 | 360 | 算法 实习 | 0 |
| q11 | 小米 | 校园招聘 大模型 算法 | 0 |
| q12 | MiniMax | 大模型 实习 | 8 |
| q13 | 字节跳动 | 后端 实习 | 6 |
| q14 | 腾讯 | 产品 实习 | 1 |
| q15 | 阿里巴巴 | 前端 实习 | 0 |
| q16 | 美团 | 数据分析 实习 | 5 |
| q17 | 小红书 | 产品 实习 | 6 |
| q18 | 哔哩哔哩 | 运营 实习 | 8 |
| q19 | 京东 | 后端 校招 | 0 |
| q20 | 快手 | 推荐算法 实习 | 0 |
| q21 | Kimi | 大模型 实习 招聘 | 0 |
| q22 | 携程 | 后端 开发 实习 | 0 |
| q23 | 网易 | 大模型 算法 实习 | 2 |
| q24 | 华为 | 大模型 算法 实习 | 1 |
| q25 | 拼多多 | 后端 开发 实习 | 0 |

## 3. 优化前后对比

上一轮（M2-R3）结果：55 条唯一候选、7 家企业、Tavily 52 条。

本轮（M2-R3.1）：**69 条唯一候选、9 家企业、Tavily 66 条**。

新增有效覆盖：

- MiniMax：0 → 8（飞书 ATS 租户）；
- 哔哩哔哩：0 → 11；
- 网易：0 → 2；
- 华为：0 → 1。

本轮阿里巴巴和得物为 0；诊断显示它们有官方详情候选，但被关键词/岗位方向过滤（分别为 2 条和 1 条）。这是当前过滤策略的保守结果，不能把已有历史候选当作本轮新发现。

## 3.1 详情核验

M2-R3.2 已对其中 8 条候选执行用户主动提取：5 条成功生成 Verified Job，3 条失败。详见 [`M2_R3_2_JD_VERIFICATION.md`](M2_R3_2_JD_VERIFICATION.md)。

## 4. 0 结果诊断

| 企业 | 真实原因 |
|---|---|
| DeepSeek | Tavily 只返回官方入口/列表页，未返回详情 |
| 360 | 有详情候选但被关键词/方向过滤；另有无效 URL |
| 小米 | 返回大数据岗位详情，与请求的 LLM 方向不匹配后过滤 |
| 京东 | 只返回校招首页/项目入口，没有稳定详情 |
| 快手 | 只返回招聘入口，没有稳定详情 |
| Kimi | Moka 租户已配置，但 Tavily 只返回列表页；未把列表当职位 |
| 携程 | Moka 租户已配置，但 Tavily 只返回列表页；未把列表当职位 |
| 拼多多 | 有详情候选但被关键词/城市/方向过滤 |
| 阿里巴巴 | 详情候选存在，但未通过关键词/城市/方向过滤 |
| 得物 | 同上 |

诊断字段由 `/jobs/discover` 的 `search.diagnostics[]` 返回：

- `raw_results`
- `detail_candidates`
- `accepted`
- `dropped_list_or_landing`
- `dropped_unrelated`
- `dropped_invalid`
- `dropped_filter`
- `provider_errors`
- `layers`
- `reason`

前端 `/discover` 会显示 0 结果原因，不再简单显示“暂无招聘”。

## 5. URL 识别与安全

新增分类：

- `official_job_detail`
- `official_job_list`
- `trusted_ats_job_detail`
- `trusted_ats_job_list`
- `recruitment_landing_page`
- `unrelated_page`
- `unverified`

实际规则：

- 精确 hostname 匹配，拒绝 `official.com.evil.test`；
- 仅 https、常规端口、无凭据；
- ATS host 必须匹配已配置的企业租户路径；
- 飞书 MiniMax 详情必须匹配 `/379481/.../position/<id>/detail`；
- Moka 详情必须匹配 `/apply/moonshot/148506#/job/<id>` 或 `/campus-recruitment/trip/117988#/job/<id>`；
- 列表、首页和带 `positionName/page/keyword` 的搜索页不会进入 JobLead；
- 带职位 ID 的查询参数会保留，用于去重；
- 不把列表页或招聘入口当成某个职位；
- 不声称彻底解决 DNS rebinding；实际网络访问继续使用受限 HTTP 客户端。

## 6. 发现与核验边界

- 所有 Tavily/ATS 结果仍是 `JobLead`；
- Tavily 摘要不是完整 JD；
- 搜索引擎日期不被当成官网发布日期；
- 只有百度官方详情页有自动完整核验；
- Tavily 结果的详情核验成功率为 **未测量/N/A**；
- Kimi/Ctrip 的 ATS 入口已验证，但动态职位列表没有可靠的详情抓取；
- 未使用登录态、Cookie、验证码绕过或批量反爬。

## 7. 推荐

- **默认搜索**：Tavily；
- **官方兜底**：百度官方公开列表；
- **ATS 来源**：MiniMax 飞书租户、Kimi/Ctrip Moka 租户，仅限已配置路径；
- 不接入其他搜索 API；
- 继续保持 `JobLead` 与 `Job` 分离；
- 对于只返回列表的 ATS，后续可评估官方公开接口或允许的详情提取，但本轮不实现。

## 8. 复现

```bash
EVAL_EMAIL=m2r31-eval@example.com \
EVAL_REGISTER=1 \
backend/.venv/bin/python scripts/m2r3_search_evaluation.py
```

无 Tavily Key 时脚本应报告来源不可用，不能生成候选。
