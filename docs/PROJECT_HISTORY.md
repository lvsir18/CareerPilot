# CareerPilot 关键版本演进

从本地完整开发记录中选取 **16 个真实版本节点**，重建可公开的脱敏阶段快照。最早可用记录从 2026-10-23 的 M6 个人版基线开始，后续覆盖 2026-11-17 的开源准备。

当前工作台与公开网站仍以 `main` 为准。原有公开提交保留，选摘历史通过合并接入，没有强制覆盖 `main`。

## 如何理解这些记录

- 每个阶段取自对应原始节点的实际源码快照，阶段间包含区间内的其他修正，未向旧版本回填后来的功能。
- 排除 `.env`、上传内容、备份、浏览器证书与字体缓存、运行日志、抓取快照及阶段测试证据；个人邮箱、已知个人 IP 和本地路径做了替换。
- 统一补充当前 MIT 许可与忽略规则，原始内部状态日志换成阶段摘要。
- 保留原记录的作者时间；公开提交的提交者时间是本次整理时间，作者身份统一为维护者的 GitHub noreply 地址。
- 这是整理后的公开历史，哈希与本地原始记录不同；下表的“本地来源”仅作对照，点击“公开版本”可查看实际代码及改动。
- 历史版本未逐一重跑现行测试，不作为当前部署版本。最新代码、手册和 CI 结果请查看 `main`。

## 关键节点

| 日期 | 阶段 | 主要改动 | 本地来源 | 公开版本 |
|---|---|---|---|---|
| 2026-10-23 | M6 个人版基线 | 账号、岗位库、画像匹配、异步 Agent、邮件与备份恢复的最早可用基线 | `17897c4` | [`29695c6`](https://github.com/lvsir18/CareerPilot/commit/29695c698a769c3d014b5b670cb711eb3a53d91a) |
| 2026-10-23 | 接入企业官方直连与关键词检索 | 腾讯官方接口，以及字节、小红书、B站、美团的官方检索 | `f22ce7d` | [`38fe581`](https://github.com/lvsir18/CareerPilot/commit/38fe5812d95e3b22768d9ea4f5e93374a515e24a) |
| 2026-10-23 | 首轮真实体验修复与求职闭环 | 修复 14 项体验问题，补齐画像确认、日历与匹配流程 | `cb24254` | [`1fe9fdf`](https://github.com/lvsir18/CareerPilot/commit/1fe9fdfbcb085fd48e356159e9d4a6622f9712a5) |
| 2026-10-24 | 第二轮 HITL、取消与多轮会话修复 | 修正画像确认绕过、取消、续传与工具会话并发等问题 | `c1f3d8b` | [`571f191`](https://github.com/lvsir18/CareerPilot/commit/571f1917e89328cfbf0a2e685caf1249e6b27f2f) |
| 2026-10-24 | 第三轮体验、跨账号草稿与预约边界 | 汇总第三轮连续复核，修复条件交接、会话加载、预约改期等边界 | `2111c98` | [`83f82d2`](https://github.com/lvsir18/CareerPilot/commit/83f82d27581d8d60bab22904c60eb52d97dc8871) |
| 2026-10-24 | 企业目录扩展与京东、MiniMax 直连 | 覆盖企业支持状态，为暂未适配的企业提供官方招聘入口 | `70f31d1` | [`0a060ad`](https://github.com/lvsir18/CareerPilot/commit/0a060ada9f911e35a21b21a7012c30936af9ab3a) |
| 2026-10-25 | 简历章节解析与项目时间维护 | 区分实习与项目，正确应用画像，并支持手动填写项目时间 | `d1d2f20` | [`e083283`](https://github.com/lvsir18/CareerPilot/commit/e083283a00d7cc69925c80d9dd83fa650a73a2bc) |
| 2026-10-25 | 12 家企业 JD 导入完整性与招聘入口 | 修复灰色企业的正文截断、描述与要求拆分，以及 DeepSeek 招聘链接 | `3fc8dbb` | [`dbfb18d`](https://github.com/lvsir18/CareerPilot/commit/dbfb18d1efbab014c252995404fd2c11849a5282) |
| 2026-10-28 | 多段教育经历与学历年份解析 | 支持多段教育，补全专业、入学与毕业年份 | `4b59851` | [`bed5604`](https://github.com/lvsir18/CareerPilot/commit/bed560414a58d840773429127fcf0f24ab67dd8d) |
| 2026-10-29 | Agent 工具进度、逐轮卡片与工作台布局 | 增加工具事件、修复运行恢复与卡片归属，解决会话栏遮挡 | `0b86570` | [`082ec72`](https://github.com/lvsir18/CareerPilot/commit/082ec725297dcad7d98d8ea8fc9fb93a1e73d741) |
| 2026-11-05 | 多轮条件继承、任务恢复与上下文裁剪 | 重启后回收任务，支持追问和结果回看，并控制长会话状态增长 | `bba8055` | [`854d34a`](https://github.com/lvsir18/CareerPilot/commit/854d34afb41af5aa2fa8fb251dfa7e5fd67a3f9b) |
| 2026-11-13 | 岗位手动更新、增量复核与软归档 | 增加明确下线判定、冷却与增量扫描，后台任务可跨页面跟随 | `c58a8ff` | [`ab50846`](https://github.com/lvsir18/CareerPilot/commit/ab5084667e0e8c354b988c2e61834f5f6e04ce42) |
| 2026-11-14 | 手机同源访问与个人模型、搜索 Key 隔离 | 修复手机与 SSE 代理访问，支持个人 Key 和共享 Key 管理员边界 | `7ef2ba2` | [`adb37b5`](https://github.com/lvsir18/CareerPilot/commit/adb37b5954b53b3fe06cc0ab12e1999e961b2159) |
| 2026-11-16 | 结构化 JD、深度发现与企业批量核验 | 补齐部门、发布时间与招聘项目，支持翻页、批量核验、取消和恢复 | `28443a8` | [`c485e2f`](https://github.com/lvsir18/CareerPilot/commit/c485e2f6d6a3c76766a1cda811291b36061c6cd6) |
| 2026-11-17 | 岗位方向多标签与八大类筛选 | 标题优先分类，统一方向大类并兼容旧分类值 | `ebec6d1` | [`2ff6edb`](https://github.com/lvsir18/CareerPilot/commit/2ff6edb274068bb62f01546ae445eacfc15b5f54) |
| 2026-11-17 | 开源规范与完整用户手册 | 补齐 MIT、贡献与安全规范、仓库模板，扩写 16 章手册 | `fbfd50f` | [`8e789d4`](https://github.com/lvsir18/CareerPilot/commit/8e789d4a6d499018cd33dd4a0b5364c0f8d2a927) |

## 与首次公开版本衔接

里程碑分支末尾使用一个对齐提交 [`19201bf`](https://github.com/lvsir18/CareerPilot/commit/19201bfb28a82758e9912d3a81a1ddfba460de17)，其文件树与现有公开版本 `dc96161` 完全相同。它只连接历史，确保合并时不会回退业务代码、网站或配置。

- [`1463fde`](https://github.com/lvsir18/CareerPilot/commit/1463fde0d787ad3f932d6455094030a6f442cae1)：首次公开源码、演示图与免登录文档站。
- [`dc96161`](https://github.com/lvsir18/CareerPilot/commit/dc961615a925cef773f681522008085a74556892)：固定抽取回退测试的离线前提，消除云端对真实招聘网页的依赖。

[查看里程碑分支](https://github.com/lvsir18/CareerPilot/tree/history/milestones) · [查看 main 提交记录](https://github.com/lvsir18/CareerPilot/commits/main/) · [在线用户手册](https://lvsir18.github.io/CareerPilot/guide/)
