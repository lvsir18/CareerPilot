# M3 匹配质量与端到端评测

> 日期：2026-10-22
> 原则：不伪造 Recall / NDCG / 准确率等需要人工标注的指标。

## 1. 自动化测试覆盖

后端 198 passed，前端 25 passed。M3 相关测试：

| 测试文件 | 覆盖 |
|---|---|
| test_resume_parser.py | PDF/DOCX 提取、字段解析、技能标准化、脱敏、扫描版 |
| test_resume_api.py | 上传/列表/删除/主简历、格式校验、跨用户隔离 |
| test_profile_m3.py | 确认/版本/内容哈希、简历应用画像、跨用户隔离 |
| test_job_features.py | Required/Preferred/Mentioned、学历、毕业年份 |
| test_matching_service.py | 技能评分、资格判断（毕业年份/学历）、basic match |
| test_matches_api.py | 完整匹配、推荐、版本重算、JobLead basic、跨用户隔离 |

## 2. 真实端到端验证（场景 A–E）

在真实 PostgreSQL + 真实 API 上执行（非 mock）：

### 场景 A：完整 JD 匹配

- 上传简历 → 解析（skills: transformer/langchain/pytorch/python/llm/rag）→ 应用到画像 → 确认（version 2）。
- 匹配百度「Agent策略工程师」：

```json
{
  "match_score": 44,
  "eligibility_status": "eligible",
  "matched_skills": ["llm", "agent"],
  "unverified_skills": ["sft", "dpo", "rlhf"],
  "strengths": ["具备岗位要求的主要技能"],
  "gaps": ["简历未体现部分必需技能"],
  "explanation": "具备岗位要求的主要技能；简历未体现部分必需技能"
}
```

### 场景 B：只有搜索摘要的 JobLead

- 匹配公开 JobLead，返回 `match_level=basic`、`match_score=null`、`explanation="招聘信息不完整，仅提供基础匹配"`，不伪造完整技能评分。

### 场景 C：画像修改

- 修改技能并重新确认后 `version` 递增，重新匹配返回新结果（MiniMax 岗 score 60 → 32）。

### 场景 D：已申请岗位

- 登记申请后，推荐接口返回 `applied_status=applied`，不修改状态时间线。

### 场景 E：跨用户隔离

- 用户 B 的简历列表为空、画像 skills 为空、version=0，无法读到用户 A 的数据。

## 3. 真实数据状态

- 已核验岗位：8 条（M2-R3.2 保留）；
- M3 验证后用户/申请/简历/匹配缓存已清理为 0。

## 4. 评测边界（诚实声明）

- 尚未建立 30 组人工标注的（画像, JD, 相关性等级）数据集；
- 因此**不输出 Recall、NDCG@K 等排序指标**；
- 技能提取准确率、硬性条件识别正确率需要人工标注后才能量化；
- 当前保证的是：`heuristic_v1` 可解释、可回归、可重复计算。

## 5. 性能（本地单机，真实执行）

- 单岗位匹配：毫秒级（规则计算 + 一次缓存查询）；
- 批量推荐：受限于已核验岗位数量，当前 8 条规模下为毫秒级；
- 未做大规模压测，不声明高并发性能。

## 6. 后续 M4 准备

- 简历解析、画像、JD 特征、匹配均为可独立调用的 Python Service；
- Scorer 通过 `MatchScorer` Protocol 抽象，后续可替换 Embedding/Reranker/学习排序；
- 匹配结果已版本化，M4 Agent 可直接消费。
