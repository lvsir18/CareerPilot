# 首次开源发布说明

目标仓库：[lvsir18/CareerPilot](https://github.com/lvsir18/CareerPilot)。本文件说明如何准备发布材料，导出脚本不会提交或推送。

## 默认公开范围

- 前后端源码、迁移、合成测试、Docker 配置、运维脚本与 CI。
- LICENSE、贡献指南、安全说明、行为准则、Issue 与 PR 模板。
- README、使用手册、公开状态摘要、M2–M6 技术说明、项目技术复盘。
- 独立演示环境截图与采集清单，位于 `apps/web/public/guide/`。

技术阶段文档可能与最新实现有差异，应结合日期与当前代码阅读。岗位来源、网页内容、第三方库不因本项目采用 MIT 而改变其自身许可。

## 默认排除范围

- `.env`、私钥、数据库、上传简历、备份、依赖目录、构建产物。
- `docs/testing/`、`docs/evidence/`、阶段体验报告与抓取网页快照。
- 完整内部迭代日志。导出时用 `PUBLIC_STATUS.md` 生成公开版 `IMPLEMENTATION_STATUS.md`，使 README 与 AGENTS 的入口仍有效。
- 本地 `.git` 历史及其作者邮箱、已删除文件。

不删除或改写原仓库里的上述文件；发布目录是独立副本。

## 生成供复核的目录

在项目根目录执行（Python 3.12+，只依赖标准库）：

```bash
python3 scripts/export_open_source.py --output dist/open-source/CareerPilot
```

脚本基于 Git 中已跟踪文件与未忽略的新文件选择工作区当前内容。因此，未提交的改动也会进入导出。目标目录已存在时会拒绝覆盖；重新导出请指定新的目录。检查 `RELEASE_MANIFEST.json` 的文件清单与哈希。导出规则不能取代人工审阅或专用 secret scanner。

## 发布前核对

1. 在新目录核对 `.env.example` 只有占位值，截图仅含演示内容，并运行项目质量检查。
2. 检查 README、手册图片与相对文档链接；根据真实运行结果更新状态，不把历史测试数量写成当前保证。
3. 在 GitHub 仓库的安全设置里启用私密漏洞报告，确认 `SECURITY.md` 的入口可用。
4. 为发布目录建立独立初始提交，核对提交作者邮箱（需要隐私时使用 GitHub noreply 地址），再推送到空仓库。保留本地开发仓库原历史。
5. 发布后再检查 CI、Issue 模板与移动端图片。仓库 Description 可随时修改，建议：

   > 面向国内实习与校招的个人求职工作台：官方岗位发现与核验、可解释匹配、Agent 多轮助手、投递看板与面试日历，支持本地私有部署。

是否采用独立初始提交、是否公开发布，由维护者最终决定；首次发布使用经过复核的独立目录，不携带本地开发历史。

## 文档界面参考

参考 [Open WebUI Quick Start](https://docs.openwebui.com/getting-started/quick-start/) 的部署与日常使用分层，以及 [Fumadocs UI](https://www.fumadocs.dev/docs/ui) 的搜索、侧边导航与页内目录组织。实现使用现有 Next.js、Tailwind 与 Lucide；没有复制对方的品牌素材或引入新的文档框架。

## 公开网站

公开站源码位于 `apps/site/`，与本地手册共享内容与截图；`.github/workflows/pages.yml` 自动构建部署。首次公开推送后，在 Settings → Pages 把 Source 设为 GitHub Actions，再运行 Public website 工作流。详见 [公开站说明](PUBLIC_WEBSITE.md)。
