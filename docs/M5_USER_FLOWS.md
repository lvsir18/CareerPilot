# M5 用户流程

## 流程 A：招聘信息检索

```text
登录 → /discover
  → 选择企业（多选）/城市/类型/方向
  → 提交搜索（触发 Tavily）
  → 卡片/表格查看
  → 点击详情 / 官网
  → 收藏（/saved-jobs）
```

- 筛选条件写入 URL（`q/companies/city/job_type/job_family/verification/published_within/days/sort/view`）
- 刷新/返回保留筛选
- 完整 JD 与 JobLead 摘要分层展示
- 搜索状态与诊断可见

## 流程 B：求职进度

```text
/applications
  → 视图切换（列表/表格/看板）
  → 创建申请 / 修改状态
  → /applications/[id] 查看时间线与证据
  → /dashboard 统计自动更新
  → /calendar 显示未来笔试/面试
```

## 流程 C：进度邮件导入

```text
/applications
  → 选择单个或多个 .eml（单批 ≤20）
  → 逐条解析并显示结果（成功/重复/失败）
  → 用户核对企业与岗位、选择申请记录
  → 确认写入时间线
  → Dashboard/Calendar 联动
```

- 低置信度进入 `needs_review`
- 重复邮件幂等（duplicate=true）
- 邮件发送时间不等于面试开始时间

## 流程 D：智能匹配

```text
上传简历 → /resumes 解析 → 应用到画像 → /profile 确认
  → /matches 查看 heuristic_v1 分数、命中技能、缺口
  → 收藏 / 登记申请 / 官网
```

## 流程 E：Agent 联动

```text
/discover「询问 Agent」→ /agent?q=...
  → Agent 多 Agent 搜索/匹配/进度
  → 「在招聘中心查看」→ /discover
```

- Agent 与可视化页面共享画像、收藏、申请、匹配数据
- Agent 不修改未经确认的申请状态
