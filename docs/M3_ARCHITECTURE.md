# M3 智能岗位匹配系统架构

> 日期：2026-10-22
> 阶段：M3 完成（不引入 LangGraph、不训练模型）

## 1. 总体流程

```text
PDF / DOCX 简历上传
    → ResumeService / ResumeParser（确定性解析）
    → 候选解析结果
    → 用户查看 / 编辑 / 确认
    → CandidateProfile + JobPreference（版本化）
    → Job 完整 JD 特征提取（JobFeatureService）
    → HeuristicV1Scorer（可解释规则评分）
    → MatchRecord（版本化缓存）
    → /matches 推荐 API
    → 前端 /resumes、/profile、/matches
```

## 2. 模块划分

```text
backend/app/services/
├── resume_parser.py        # PDF/DOCX 文本提取 + 规则解析
├── resume_service.py       # 上传、列表、删除、设主简历、应用到画像
├── profile_service.py      # 画像/偏好 CRUD、确认、版本、内容哈希
├── skill_normalizer.py     # 技能同义词标准化（可扩展）
├── job_feature_service.py  # JD Required/Preferred/Mentioned 技能、学历、毕业年份
├── matching_service.py     # HeuristicV1Scorer + basic_match
└── recommendation_service.py # 单/批量匹配、缓存、推荐

backend/app/db/models/
├── resume.py               # Resume
├── match_record.py         # MatchRecord（版本化缓存）
└── profile.py              # CandidateProfile / JobPreference 扩展

backend/app/api/v1/
├── resumes.py              # POST/GET/DELETE /resumes
├── profile.py              # /profile/me、/confirm、/apply-resume
└── matches.py              # /matches/jobs/{id}、/job-leads/{id}、/recommendations
```

## 3. 数据模型

### 3.1 Resume

| 字段 | 说明 |
|---|---|
| user_id | 用户隔离，CASCADE |
| filename / content_type / size | 文件元数据 |
| storage_key | 私有对象存储 key（本地文件系统） |
| text | 提取的纯文本（不输出日志） |
| parse_status | pending / success / failed |
| parsed_json | 结构化解析结果 |
| error | 解析失败原因 |
| is_primary | 是否作为画像主要来源 |

### 3.2 CandidateProfile 扩展

在原 M1 基础上新增：

- `experiences_json`：实习/项目/科研/竞赛/开源经历；
- `content_hash`：画像内容哈希；
- `confirmed_at`：确认时间。

原字段：`headline`、`skills_json`、`education_json`、`projects_json`、`version`、`verified_by_user`。

### 3.3 JobPreference 扩展

新增：

- `target_roles_json`：目标岗位方向（用于岗位方向匹配）；
- `available_start_date`、`internship_duration_months`、`internship_days_per_week`；
- `graduation_year`、`remote_ok`。

原字段：`cities_json`、`job_types_json`、`keywords_json`、`excluded_keywords_json`、`target_companies_json`。

### 3.4 MatchRecord（版本化缓存）

| 字段 | 说明 |
|---|---|
| user_id | 用户隔离 |
| job_id / job_lead_id | 匹配目标（二选一） |
| profile_version | 画像版本 |
| profile_content_hash | 画像内容哈希 |
| job_content_hash | JD 内容哈希（Job.content_hash） |
| scorer_version | heuristic_v1 |
| match_level | full / basic |
| result_json | 完整匹配结果 |

失效条件：画像版本变化、JD 内容哈希变化、scorer 版本变化。用户私有数据不跨用户共享。

## 4. 服务接口（供 M4 复用）

M4 LangGraph Agent 直接调用以下服务，而不是在 Agent 内重新实现：

```python
parse_resume(content: bytes, filename: str) -> ParsedResume
extract_job_features(job: Job) -> JobFeatures
HeuristicV1Scorer().score(profile: ProfileRead, job: Job) -> MatchResult
basic_match(lead: JobLead) -> MatchResult
RecommendationService.match_job(...)
RecommendationService.recommendations(...)
```

## 5. 安全与隐私

- 简历、画像、匹配结果按 user_id 隔离；
- 写操作沿用 CSRF；
- 简历文件大小默认 ≤10MB，校验扩展名与实际格式；
- 原始文件写私有存储（0600 权限），不生成公开 URL；
- 完整简历文本不进普通日志；
- 联系方式（邮箱/手机）解析时脱敏；
- 删除简历同时删除原始文件；
- 岗位 JD 是外部非可信内容，只做文本规则解析，不作为指令执行；
- 匹配服务不修改申请状态。

## 6. 已知限制

- 扫描版 PDF 不强制 OCR，提示用户手动粘贴；
- 学历/毕业年份/技能的规则解析是确定性的，可能漏识别或误识别；
- `heuristic_v1` 权重是初始规则，不是统计最优，不代表录取概率；
- 基础匹配（JobLead）不输出百分制分数。
