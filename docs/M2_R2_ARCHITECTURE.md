# M2-R2 个人招聘进度管理架构

> 版本：2026-10-21  
> 范围：申请进度、状态时间线、手动/链接/JobLead 登记、`.eml` 邮件导入、邮箱与浏览器接口预留  
> 不在范围：自动投递、自动填表、招聘平台密码/Cookie 托管、登录态批量采集、M3 匹配、M4 Agent

## 1. 复用与增量

复用：

- M1 `Application` / `ApplicationEvent`；
- M1 认证、CSRF、用户隔离；
- M2-R1 `JobLead`、`Job`、`SourceEvidence`；
- 现有 `/applications` 页面与状态控件。

增量：

- `Application` 支持 Job / JobLead / 仅官方 URL 三种目标；
- 申请与事件增加来源、证据、确认时间、去重键；
- 新增 `application_imports` 邮件预览/确认表；
- 新增 `.eml` 安全解析服务；
- 前端新增链接登记、邮件导入、时间线、筛选与待核实提示。

## 2. 状态设计

保留 M1 旧值以避免破坏历史数据，同时新增产品要求的规范状态：

| 规范状态 | 说明 |
|---|---|
| `saved` | 已收藏 |
| `planned` | 计划申请 |
| `applied` | 用户确认已申请 |
| `screening` | 简历筛选中 |
| `assessment` | 笔试/测评 |
| `interview` | 面试中 |
| `offer` | 收到 Offer |
| `rejected` | 流程结束/未通过 |
| `withdrawn` | 用户撤回 |
| `unknown` | 状态未知 |

兼容旧值：`to_apply`、`preparing`、`online_assessment`、`closed`。新操作使用规范状态；旧记录不迁移删除。

**打开官网链接不会创建申请或事件。** 用户必须点击登记/确认。

## 3. 数据模型

### Application 增量

- `job_id` 可空；
- `job_lead_id` 可空，关联 M2-R1 候选；
- `external_company/title/url`：官方链接登记快照；
- `source_type`：`manual` / `email_import` / `official_api` / `browser_assisted`；
- `source_reference`；
- `last_confirmed_at`；
- `dedupe_key`：`(user_id, dedupe_key)` 唯一；
- 约束：Job、JobLead、外部 URL 至少一个；外部 URL 必须 http/https。

### ApplicationEvent 增量

- `event_time`：事件发生时间（区别于 `created_at` 入库时间）；
- `source_type`；
- `source_reference`；
- `evidence_summary`；
- `verification_status`：
  - `user_reported`
  - `email_confirmed`
  - `website_user_confirmed`
  - `official_api`
  - `unverified`

`from_status` / `to_status` 保留，用于兼容 M1；API 同时返回 `previous_status` / `new_status`。同一 `(application_id, source_type, source_reference)` 唯一，保证重复确认幂等。

### ApplicationImport

只保存预览所需的最小字段：主题、发件人、日期、解析企业/岗位/状态/时间、置信度、匹配申请、脱敏正文摘要。**不保存完整原始邮件，不写日志正文。**

唯一约束 `(user_id, content_hash)` 用于识别重复 `.eml`。

## 4. 邮件导入安全边界

- 仅接受 `.eml`，大小上限 **2 MB**；
- 使用 Python `email` 标准库解析，不执行 HTML/脚本，不加载外部图片/资源；
- HTML 仅作为文本提取，`script`/`style` 内容丢弃；
- 不把邮件正文交给 LLM 或 Agent；
- 解析结果先预览，`POST /confirm` 后才写入事件；
- 邮件没有明确状态时 `parsed_status=null`，确认时必须由用户选择；
- “简历已接收”只提示收到简历，不推断通过筛选；
- 无法唯一匹配申请时必须由用户选择；
- 用户 A 不能读取/确认用户 B 的导入。

## 5. 来源可信等级

| 场景 | source_type | verification_status |
|---|---|---|
| 用户手动登记/改状态 | `manual` | `user_reported` |
| 用户上传并确认邮件，邮件明确状态 | `email_import` | `email_confirmed` |
| 用户确认邮件但选择的非邮件明确状态 | `email_import` | `user_reported` |
| 未来官网/插件用户确认 | `browser_assisted` | `website_user_confirmed` |
| 未来官方 API | `official_api` | `official_api` |

当前公开 API **只接受 manual 事件**；邮件证据由导入确认服务写入。浏览器/官方 API 仅保留协议与数据字段，未启用。

## 6. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/applications` | 列表；`status`、`company`、`query`、分页 |
| POST | `/api/v1/applications` | Job/JobLead/官方链接登记 |
| GET | `/api/v1/applications/{id}` | 详情 + 完整时间线 |
| PATCH | `/api/v1/applications/{id}` | 备注/外部岗位快照 |
| GET | `/api/v1/applications/{id}/events` | 时间线 |
| POST | `/api/v1/applications/{id}/events` | 用户确认的事件（manual） |
| PATCH | `/api/v1/applications/{id}/status` | 兼容 M1 的状态更新 |
| POST | `/api/v1/application-imports/email` | 上传 `.eml`，只预览 |
| GET | `/api/v1/application-imports` / `/{id}` | 本人的导入记录 |
| POST | `/api/v1/application-imports/{id}/confirm` | 用户确认后写事件（幂等） |

所有写接口沿用 M1 CSRF；所有查询按 `user_id` 隔离。

## 7. 未来接口（设计）

### EmailConnector

`backend/app/connectors/email.py` 定义：

- `connect`
- `disconnect`
- `connection_status`
- `list_recruitment_messages`
- `sync_application_events`

没有真实 OAuth provider/凭据，当前没有 `/mail-connections/start` 可用实现，也不显示“已连接”。

### BrowserProgressImporter

`backend/app/connectors/browser.py` 定义只读当前页面、用户确认后导入的接口。未来 MV3 插件必须：

- 仅在用户主动点击时读取当前已登录页面；
- 只上传与本人申请相关的用户确认字段；
- 不上传 Cookie/Token/密码；
- 不后台轮询、不绕过 CAPTCHA/风控。

当前未实现插件，公开 API 不接受 browser 证据。

## 8. 已知限制

- 邮件导入不自动匹配所有企业；无法确定时必须人工选择；
- 只支持 `.eml`，不支持直接连接邮箱；
- 邮箱 OAuth 接口只是协议，未接入真实 Gmail/Outlook/IMAP；
- 浏览器插件未实现；
- 邮件正文摘要会保存在用户私有数据库，未做字段级加密（部署方可使用磁盘/数据库加密）；
- 人工状态和邮件状态仍可能有误，UI 保留待核实标记，不自动推断拒绝；
- 不提供自动投递、自动填表或第三方账号密码托管。
