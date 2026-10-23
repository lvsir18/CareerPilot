# M2 中国招聘数据源调研

> 调研日期：2026-10-21  
> 调研范围：P0 十家 + P1 九家；2026-10-21 已在线校验官方招聘根域名和公开 ATS 入口，详情页自动核验仍只有百度。  
> 结论口径：**“技术上可抓取”不等于“获得授权”**。未找到明确开放、允许本项目用途的接口时，一律标记为阻塞，不使用内部接口、不绕过反爬。百度公开详情页采用“用户提交单链接、单次读取”的保守模式，不代表获得批量抓取许可。

---

## 1. 结论摘要

| 数据源 | 官方入口 | 页面形态 | 明确公开 API | 可用接入方式 | 处理 |
|---|---|---|---|---|---|
| 字节跳动 | jobs.bytedance.com | SPA，无 SSR / JSON-LD | 未发现公开文档；站点使用需 CSRF 的 `/api/v1/search/job/posts` | 无 | 阻塞，不实现内部接口 |
| 腾讯 | join.qq.com | SPA（`<div id="app">`） | 未发现官方文档；第三方使用未公开的 join.qq.com XHR | 无 | 阻塞 |
| 阿里巴巴 | talent.alibaba.com | SPA | **有**：淘宝开放平台 `alibaba.recruit.website.jobs.search`、`alibaba.recruit.position.pagesearch`，标注免费、不需要用户授权 | 官方 API（需企业凭据） | 已实现凭据门控 Connector，未配置时显示“未配置” |
| 美团 | zhaopin.meituan.com / career.meituan.com | SPA 加载壳 | 未发现公开文档 | 无 | 阻塞 |
| 百度 | talent.baidu.com | **服务端渲染 HTML**（列表/详情均内嵌 `window.__INITIAL_DATA__`） | 无需登录即可读取公开详情页；使用用户提交的单链接，不做批量 | 用户提交单链接 | **M2-A 已接入并在线验证** |

**M2-A 已用百度官方公开详情页完成真实岗位在线验证；这不等于获得了批量抓取许可。** 批量 P0 同步仍未完成，其他企业继续阻塞。

### 1.1 M2-R1 搜索优先更新（2026-10-21）

- 已实现可替换 licensed search provider：`brave`、`bing`、`google`（key 仅环境变量配置，未硬编码）；
- 当前环境未配置任何 licensed search key，因此 `licensed_configured=false`；
- 实际发现使用 `baidu_official_list`：只读 `talent.baidu.com/jobs/list` 第一页的公开 SSR 数据；
- 真实运行：查询“实习”、企业百度，发现 10 条官方候选链接，尝试核验 3 条、成功 3 条，7 条保留待核验；
- 候选链接与核验 Job 分离；搜索摘要不作为完整 JD；

### 1.2 M2-R3.1 搜索增强、ATS 与 Provider 状态（2026-10-21）

- Tavily Search API：**唯一 licensed 搜索 Provider**；`SEARCH_PROVIDER=tavily` + `TAVILY_API_KEY`。已完成真实 25 条查询。
- 百度官方公开列表页：Tavily 的兜底来源，仅读第一页。
- 多企业、城市、实习/校招、岗位方向和分页筛选已接入 `/jobs/discover`；25 条固定查询真实评测见 [`M2_R3_SEARCH_EVALUATION.md`](M2_R3_SEARCH_EVALUATION.md)。
- 可信 ATS：MiniMax 飞书租户 `vrfi1sk8a0.jobs.feishu.cn`；Kimi Moka 路径 `/apply/moonshot/148506`；携程 Moka 路径 `/campus-recruitment/trip/117988`。只绑定这些租户/路径，不信任整个 `jobs.feishu.cn` 或 `app.mokahr.com`。
- 2026-10-21 真实 Tavily 评测：Tavily 发现 66 条唯一候选，覆盖字节、小红书、B站、美团、MiniMax、腾讯、网易、华为；百度兜底 3 条；合计 69 条，全部为 `JobLead`，未自动核验。阿里巴巴、得物、DeepSeek、360、小米、京东、快手、Kimi、携程、拼多多本轮无候选。

官方来源目录（在线校验 2026-10-21，根域名 HTTP 200）：

| 优先级 | 企业 | 域名 | 详情核验 |
|---|---|---|---|
| P0 | 字节跳动 | jobs.bytedance.com | 人工 |
| P0 | 腾讯 | join.qq.com | 人工 |
| P0 | 阿里巴巴 | talent.alibaba.com | 人工 |
| P0 | 百度 | talent.baidu.com | 百度公开详情自动核验 |
| P0 | 美团 | zhaopin.meituan.com / career.meituan.com | 人工 |
| P0 | 小红书 | job.xiaohongshu.com | 人工 |
| P0 | 哔哩哔哩 | jobs.bilibili.com | 人工 |
| P0 | 得物 | careers.dewu.com | 人工 |
| P0 | DeepSeek | talent.deepseek.com | 人工 |
| P0 | 360 | hr.360.cn | 人工 |
| P1 | 小米 | hr.xiaomi.com | 人工 |
| P1 | MiniMax | minimax.cn / www.minimax.cn + 飞书租户 | ATS 链接候选；人工核验 |
| P1 | 京东 | campus.jd.com | 人工 |
| P1 | 月之暗面 Kimi | careers.kimi.com + Moka 租户 | ATS 链接候选；人工核验 |
| P1 | 携程 | job.ctrip.com / careers.ctrip.com + Moka 租户 | ATS 链接候选；人工核验 |
| P1 | 快手 | zhaopin.kuaishou.cn / campus.kuaishou.cn | 人工 |
| P1 | 网易 | campus.163.com | 人工 |
| P1 | 华为 | career.huawei.com | 人工 |
| P1 | 拼多多 | careers.pddglobalhr.com | 人工 |

根域名可达不等于职位详情页可信，也不代表已实现批量同步；所有 Tavily 结果默认仍是 `JobLead`。

### 1.3 详情获取与核验（M2-R3.2）

- Tavily Extract 仅由用户主动触发，单 URL；
- 默认 `basic`，动态页面可使用 `advanced`；
- 5 条详情成功升级 Verified Job：MiniMax、美团、小红书、小米、网易；
- 3 条失败保留 JobLead：B站职位已下架、网易项目列表 URL、MiniMax 另一个详情 Tavily 提取失败；
- 百度继续使用公开详情页解析；
- 失败原因、最近核验时间和证据会保存；
- 中国大陆 ATS 动态页面和官方页面仍有提取失败，不做登录/反爬绕过。

---

## 2. 判定方法与合规边界

对每个来源检查：

1. 官方招聘首页与岗位入口是否可访问；
2. `robots.txt`（若存在）是否允许相关路径；
3. 服务端 HTML 是否包含岗位数据、JSON-LD `JobPosting`、`__NEXT_DATA__` 或 `__INITIAL_DATA__`；
4. 是否存在**有官方文档、允许第三方使用**的岗位 API；
5. 是否需要登录、AppKey/Secret、签名、企业租户 ID 或商务授权；
6. 是否能获得稳定 `source_job_id`、JD、城市、招聘项目与发布时间；
7. 是否有明确的关闭/变更信号。

禁用项：不调用未公开的内部 XHR、不逆向签名、不绕过验证码/风控、不采集 HR 或候选人个人信息、不使用演示数据冒充真实岗位。

> robots.txt 只表达抓取偏好，不构成数据使用授权；即使未禁止，也需要服务条款/官方许可支持。

---

## 3. 逐家调研记录

### 3.1 字节跳动（jobs.bytedance.com）

- 官方入口：`https://jobs.bytedance.com/`（校招 `/campus`、社招 `/experienced`）。
- `robots.txt`：存在，`User-agent: *`；`Allow: /experienced, /society, /campus, /en, /jp`；`Disallow: /referral`；无 Sitemap/Crawl-delay。
- 页面：`/campus/position` 与岗位详情页的静态 HTML 仅有“校园招聘”标题/壳，无岗位 DOM、无 JSON-LD、无 `__NEXT_DATA__`；岗位由 JS 异步加载。
- 接口：站点前端使用 `/api/v1/search/job/posts` 一类内部接口，历史公开文章显示还需要 `/api/v1/csrf/token` 的 CSRF 头；**未见官方开放文档或使用许可**。
- 结论：**阻塞**。`robots.txt` 允许路径不等于允许调用内部 API；不以逆向方式接入。

### 3.2 腾讯（join.qq.com）

- 官方入口：`https://join.qq.com/`、岗位页 `/post.html`。
- `robots.txt`：返回 404/SPA 页面；没有有效规则（不等于授权）。
- 页面：静态 HTML 仅 `<div id="app"></div>` + JS bundle，无岗位数据、无 JSON-LD。
- 接口：第三方资料使用 join.qq.com 的公开 XHR（无需登录），但**没有腾讯官方 API 文档/授权说明**，且站点条款未明确允许批量采集。
- 结论：**阻塞**，不将“无需鉴权”当作“已授权”。

### 3.3 阿里巴巴（Alibaba Group）

- 官方招聘站：`https://talent.alibaba.com/`（SPA；服务端仅返回 `#app` 壳）。
- 开放平台文档：
  - `alibaba.recruit.website.jobs.search`（招聘官网职位搜索）：标注“开放平台免费 API / 不需要授权”，但仍需 `app_key` + `sign` 签名。
  - `alibaba.recruit.position.pagesearch`（招聘官网职位分页）：标注“￥免费 / 不需要授权”，需要 `app_key`、`sign`、`tenant_id`；返回 `position_id`、名称、JD、要求、工作地、职类等。
  - 文档地址：`https://developer.alibaba.com/docs/api.htm?apiId=38421`、`?apiId=61394`（2026-10-21 访问）。
- 限制：
  - TOP 网关要求企业应用 `app_key`/`app_secret` 与签名，时间戳误差 ≤10 分钟；
  - `tenant_id` 由对接方提供，无法自行生成；
  - 没有可用凭据时无法完成真实调用；
  - 文档未返回发布时间；`published_at` 必须保持 `null`，不能用更新时间冒充；
  - 返回没有明确招聘状态，`status` 保持 `unknown`，不因一次未出现就关闭岗位。
- 结论：**有条件合规**。已实现 `alibaba_openapi` Connector，读取环境变量凭据，缺配置时健康检查显示“未配置”，不做任何网络请求。**未完成真实在线验证**。

### 3.4 美团（career.meituan.com / zhaopin.meituan.com）

- `robots.txt`：请求被 SPA 回退成 HTML，未得到有效规则。
- `/web/position` 与 `?pageNo=2`：仅返回 `#app-container` 加载动画，无岗位 DOM / JSON-LD。
- 招聘数据由打包 JS 通过内部接口获取；页面包含 Owl/灵犀监控与网络拦截监测。
- 结论：**阻塞**，不调用内部接口、不执行绕过风控的自动化。

### 3.5 百度（talent.baidu.com）

重新验证后确认百度招聘站采用 **服务端渲染 + 内嵌数据**，不是此前判断的纯前端空壳：

- 列表页：`https://talent.baidu.com/jobs/list?recruitType=INTERN` 与 `/jobs/list` 返回 200，HTML 约 89KB，包含 `window.__INITIAL_DATA__`；`listData.listDetailData` 有 10 条真实岗位，`total=503`、`pageSize=10`，字段含 `postId`、`jobId`、`name`、`publishDate`、`workContent`、`serviceCondition`、`workPlace`、`projectType`。
- 详情页：`https://talent.baidu.com/jobs/detail/INTERN/<postId>` 返回 200，HTML 内嵌 `detailData.postInfo`，含完整 JD、要求、日期、工作地、岗位 ID。用当前岗位 `f8f8f186-2d4a-4b55-9f6c-34018f476896` 实测可解析。
- 用户提供的示例链接 `.../22b11ac9-3920-4236-b079-49e13f5d08d3` 当前只返回 6KB 前端壳，无 `__INITIAL_DATA__`，说明该岗位已失效或结构变更；系统返回 `IMPORT_PAGE_UNREADABLE` 并支持粘贴 JD。
- `robots.txt`：`https://talent.baidu.com/robots.txt` 返回 HTTP 404（无规则）；这不等于授权，仍需遵守服务条款与访问频率限制。
- 访问边界：**只读取用户显式提交的单个详情页**，每次一个请求，不登录、不携带用户 Cookie、不翻页、不批量抓取；使用可识别 User-Agent、超时与限速。
- M2-R3 复核：列表页接收 `pageNum`、`pageSize`、`keyWord` 参数，但 SSR 返回仍为 `pageNum=1`、`pageSize=10`；不能据此实现合规翻页。当前只读第一页。
- 结论：**可作为 M2-A 的公开页面单链接导入源**。已实现 `baidu_public` Connector；M2-R1 通过官方列表页发现 10 条候选，并在线核验 3 条真实岗位（见状态文档）。M2-R3 保留这一边界，不声称同步全部 504 条。

### 3.6 第三方招聘账户连接

目前不启用任何自动登录/自动同步：

- 数据模型 `external_account_connections` 只保存 **密钥管理系统引用**（`vault://` / `secret://`），不保存密码、Cookie 或 Token；
- OAuth / 浏览器会话模式必须同时在配置中 allow-list 对应 provider；浏览器会话需额外显式开关；
- 服务按 `user_id` 隔离，支持过期自动失效、撤销时清空引用；
- 当前没有已验证的 P0 平台书面许可，因此只提供扩展接口，不实现批量登录。

### 3.7 P1 抽查

| 企业 | 观察 | 结论 |
|---|---|---|
| 华为 | `career.huawei.com` 页面为 Vue SPA，岗位列表由 JS 渲染，链接动态拼接 | 阻塞 |
| 拼多多 | `careers.pinduoduo.com` 为 Next.js，`__NEXT_DATA__` 仅含首页 CMS；岗位接口未公开 | 阻塞 |
| 京东 | `campus.jd.com` 为 Umi SPA，引用 `/api/wx/position/index` 等内部接口 | 阻塞 |
| 网易 | `campus.163.com` 返回 SPA 壳 | 阻塞 |
| 月之暗面 / 智谱 等 | 使用 Moka/自研 SPA，接口未公开 | 阻塞 |
| 海外 ATS（Greenhouse/Lever/Ashby） | 有官方公开 Job Board API，但本次目标是中国大厂官方渠道；未作为 P0 替代 | 仅保留架构兼容 |

---

## 4. 已实现的合规接入路径

### 4.0 M2-R1 搜索发现与候选

| 组件 | 说明 |
|---|---|
| `SearchService` | 站点限定查询、URL allowlist、去重、Redis 缓存/限流、超时与降级 |
| Tavily | 唯一 licensed 搜索 Provider；Key 仅环境变量；无 Key 时明确不可用；只存官方 URL/标题/短摘要 |
| `BaiduOfficialListProvider` | 单页公开列表，非 licensed API；当前真实发现来源 |
| `JobLeadService` | 公开候选/私有导入/官方核验；打开官网不改变状态 |
| `JobLead` / `SourceEvidence` | 候选与已核验 Job 分离，保留来源证据 |



1. **`baidu_public`（M2-A，已在线验证）**：
   - 用户提交百度官方详情页 URL；
   - `PublicWebsiteConnector` 只抓取该单个页面，解析 `__INITIAL_DATA__`；
   - 保存 `source_method=public_page`、`verification_status=verified`、`verified_at`；
   - 页面失效时返回 `IMPORT_PAGE_UNREADABLE`，用户可粘贴 JD 并以 `user_confirmed` 入库；
   - 不做列表翻页、批量同步或登录。
2. **`manual`**：管理员将**有权使用的官方导出 JSON** 放入 `MANUAL_IMPORT_DIR`，配置文件名后同步。
   - 只读取目录内文件，拒绝路径穿越；
   - 全部记录 `is_demo=false`，`source_method=manual_import`、`verification_status=unverified`；
   - 仍需人工确认来源合法。
3. **`alibaba_openapi`**：调用阿里官方 TOP API（免费、无需用户授权），通过环境变量提供
   `ALIBABA_APP_KEY`、`ALIBABA_APP_SECRET`、`ALIBABA_TENANT_ID` 与岗位详情 URL 模板后启用。
   - 未配置时：`/job-sources/{id}/health` 返回 `configured=false`，同步任务失败并写明原因，不产生任何岗位。
   - 解析只在本地进行，使用录制响应做测试；未伪造在线成功结果。
4. **`fixture`**：仅用于离线演示，全部 `is_demo=true`，`DEMO_MODE=false` 时禁用。

Connector 模式：

- `PublicWebsiteConnector`：百度已实现（单链接）。
- `ManualImportConnector`：授权 JSON 文件。
- `AuthorizedSessionConnector`、`SearchDiscoveryConnector`：仅定义协议，未启用任何平台。
- `ExternalAccountConnection`：仅元数据与密钥引用，支持 OAuth / 浏览器会话 / 手动导入三种模式的设计，但默认全部未授权。

## 5. 完成与未完成项

已完成：

- 百度公开详情页单链接导入（M2-A），真实岗位 1 条在线入库；
- 页面不可读时的手动粘贴 + 用户确认入库；
- 来源链接、`source_method`、`verification_status`、`verified_at` 落库；
- 同一来源重复导入幂等；
- 外部账号连接数据模型/服务/API 设计，未启用自动登录。

未完成/阻塞：

- 百度列表批量抓取、自动翻页、定时同步：未实现，避免超出公开单页访问边界；
- 字节、腾讯、美团：没有明确公开 API/许可，保持阻塞；
- 阿里官方 API：缺 `app_key/app_secret/tenant_id`，未在线验证；
- 第三方账户 OAuth/浏览器会话：没有已验证的 P0 平台许可，未启用；
- 未使用任何内部接口、未绕过验证码/签名/风控。

## 6. 后续合规推进建议

1. 如需百度批量同步，先确认百度招聘服务条款/书面许可，再讨论列表页与频率限制；当前只保留单链接导入。
2. 由项目方在淘宝开放平台申请应用，获取 `app_key/app_secret` 与合作伙伴 `tenant_id`，配置后再做真实同步验收。
3. 向字节、腾讯、美团招聘合作/法务渠道申请官方数据接口或书面许可；获批前保持阻塞。
4. 若获得平台书面授权，可基于 `AuthorizedSessionConnector` / `SearchDiscoveryConnector` 实现连接器，但必须使用 `ExternalAccountConnection` 的密钥引用模式，不存明文凭据。
