# 公开介绍与文档站

CareerPilot 有两个入口：

| 入口 | 用途 | 是否需要自己的后端 |
|---|---|---|
| `https://lvsir18.github.io/CareerPilot/` | 项目介绍、演示截图、免登录手册与部署指引 | 否 |
| 自己部署的 `http://localhost:3000` | 岗位发现、画像匹配、Agent、投递与日程等完整业务 | 是 |

网站只有在完成首次推送和 Pages 配置后才可访问。公开站不提供登录、简历上传、真实搜索或在线 Agent，不存放个人求职数据。截图使用虚构演示数据，Agent 图为预置对话。

## 如何维护

公开站源码位于 `apps/site/`，使用现有 `apps/web` 的依赖。它与本地 `/guide` 共用：

- `apps/web/lib/guide-content.ts`：手册数据。
- `apps/web/components/guide-reader.tsx`：图文渲染。
- `apps/web/components/guide-navigation.tsx`：搜索与目录。
- `apps/web/public/guide/`：截图与采集清单。

公开模式将「去岗位库」等业务链接替换成对应章节说明；图片路径加上项目路径前缀。本地手册保留真实功能跳转与原有登录保护。无需维护第二份网页手册内容。

## 本地构建

建议 Node 22.13+，或当前受支持的更新版本；较旧的 Node 22.11 不能运行当前 jsdom 测试依赖。CI 固定 Node 22 主版本并安装最新补丁。

```bash
cd apps/web
npm ci
npm run site:lint
npm run site:build
```

输出在 `dist/public-site/`，包含静态 HTML / CSS / JS 和公开演示图。构建不加载根目录 `.env` 或业务后端；临时项目仅复制网站源码和截图清单指定的文件。构建临时目录与产物已加入忽略规则。

默认路径为 `/CareerPilot`。修改仓库名时，工作流使用仓库名生成 `SITE_BASE_PATH`；自定义域名根路径可将该变量设为空，同时自行修改站点元数据和仓库链接。

预览必须按真实子路径映射，不能只检查域名根目录。可把 `dist/public-site` 放到某个静态服务根目录的 `CareerPilot/` 下，然后访问 `/CareerPilot/`。

## 首次发布

1. 推送经过复核的开源版本到 `lvsir18/CareerPilot` 的 `main`。
2. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
3. 在 **Actions → Public website → Run workflow** 运行一次；也可以在启用后推送网站相关变更。
4. 等待 build 与 deploy 都成功，再打开公开首页和 `/guide/`、`/start/`。

工作流：`.github/workflows/pages.yml`。main 推送会发布；PR 只构建，不部署。部署 job 才授予 `pages: write` 与 `id-token: write`，不需要手动保存 PAT 或服务器密钥。构建产物不会包含完整应用、数据库或根目录环境文件。

## 验收

只需静态服务器，不需要启动业务服务：

```bash
cd apps/web
SITE_E2E_BASE_URL=http://127.0.0.1:13003/CareerPilot/ \
  npx playwright test --config playwright.site.config.ts
```

覆盖桌面、平板、手机，包含匿名访问、六种截图切换、原图加载、手册搜索、章节跳转、部署页、子路径链接、页面宽度和无后端 API 请求。默认配置使用本机 Chrome，首次运行前请安装 Chrome；若改为 Playwright 自带 Chromium，移除配置中的 `channel: "chrome"`，并执行 `npx playwright install chromium`。

配置与运行背景参考 [Next.js 静态导出](https://nextjs.org/docs/app/guides/static-exports) 和 [GitHub Pages 自定义工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)。
