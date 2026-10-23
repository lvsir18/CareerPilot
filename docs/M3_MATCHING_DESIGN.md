# M3 岗位匹配设计（heuristic_v1）

> 本阶段使用可解释规则匹配，不训练模型，不引入向量召回/Reranker。

## 1. JD 特征提取

从完整 JD（Job.description + requirements_json + raw_payload_json.skills）提取：

| 特征 | 说明 |
|---|---|
| required_skills | 出现在"要求/精通/熟悉/掌握/具备"上下文中的技能 |
| preferred_skills | 出现在"优先/加分/有经验者优先"上下文中的技能 |
| mentioned_skills | JD 提到的技术，但无明确要求标记 |
| degree_requirement | 本科/硕士/博士等 |
| graduation_year_requirement | 如"2027届" |

技能按行分类，避免远处标记污染。Required 优先级高于 Preferred 高于 Mentioned。

技能标准化见 `skill_normalizer.py`：`PyTorch→pytorch`、`大模型→llm`、`RAG→rag`、`LangGraph/LangChain` 分别保留。上下位技能不简单等价（PyTorch ≠ DeepSpeed）。

## 2. 评分规则

```text
MatchScore =
    0.45 × SkillScore
  + 0.25 × RoleScore
  + 0.20 × PreferenceScore
  + 0.10 × ExperienceScore
```

各维度 0–100，权重为初始规则（可配置）。

### SkillScore

- 有 Required：required 覆盖率为主 + preferred 加分（最多 +30）；
- 无 Required 但有 Mentioned：mentioned 覆盖率 × 0.6；
- 都无：0（降低结果可信度）。

### RoleScore

- 用户未设置目标方向 → 50（中性）；
- JD 方向命中目标方向 → 100，否则 0。

### PreferenceScore

- 城市：命中 100 / 未命中 0 / 未设置 50；
- 求职类型：命中 100 / 未命中 0 / 未设置 50；
- 取平均。

### ExperienceScore

- 用户经历技能与 JD 技能重叠比例；
- 无经历 → 50（中性）。

## 3. 资格判断（独立于分数）

```text
eligible   —— 满足已明确验证的资格条件
ineligible —— 明确不满足硬性条件
unknown    —— 信息不足
```

硬性条件：毕业年份要求、学历要求、求职类型约束。城市是偏好条件，不作硬性筛选。

## 4. 匹配结果结构

```json
{
  "job_id": "...",
  "scorer_version": "heuristic_v1",
  "match_level": "full",
  "match_score": 44,
  "eligibility_status": "eligible",
  "matched_skills": ["llm", "agent"],
  "unverified_skills": ["sft", "dpo", "rlhf"],
  "strengths": ["具备岗位要求的主要技能"],
  "gaps": ["简历未体现部分必需技能"],
  "evidence_coverage": 0.5,
  "explanation": "具备岗位要求的主要技能；简历未体现部分必需技能"
}
```

- `unverified_skills` 表示"简历未体现"，不等于"用户不会"；
- `match_score` 不是录取概率；
- 缺失字段不当作"不满足"。

## 5. 基础匹配（JobLead）

只有标题/摘要的 JobLead 返回：

```json
{
  "match_level": "basic",
  "match_score": null,
  "explanation": "招聘信息不完整，仅提供基础匹配"
}
```

不输出百分制得分，不与完整 JD 得分混排。

## 6. 缓存与失效

MatchRecord 键：`user_id + job_id + profile_version + scorer_version + job_content_hash`。

- 画像修改 → version +1 → 旧缓存失效；
- JD 更新 → content_hash 变化 → 失效；
- scorer 版本变化 → 失效；
- 私有 JobLead 匹配结果不跨用户。
