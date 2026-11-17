# CareerPilot 公开网站

GitHub Pages 站点：项目介绍、演示截图、公开手册与本地部署说明。不依赖 FastAPI、数据库或登录，不调用真实模型和邮箱。

## 构建

复用 `apps/web` 的 Node 工具链（建议 Node 22.13+，CI 使用最新 22.x），不用另装一套依赖。

```bash
cd apps/web
npm ci
npm run site:lint
npm run site:build
```

生成 `dist/public-site/`。构建脚本只复制公开站源码和截图清单指定的演示图，不读取根目录 `.env`、数据库或上传内容。编译临时目录在 `apps/web/.public-site-*/`，结束时自动清理，以复用已有依赖与共同手册组件。

默认 `SITE_BASE_PATH=/CareerPilot`，可在构建前设为空来部署到域名根目录。静态服务器预览时请把产物映射到 `/CareerPilot/`，避免用根路径掩盖图片与链接问题。

## 内容入口

- 首页与部署页：`app/page.tsx`、`app/start/page.tsx`
- 手册数据：`../web/lib/guide-content.ts`
- 手册组件：`../web/components/guide-reader.tsx`、`guide-navigation.tsx`
- 原始截图：`../web/public/guide/`（演示数据）

公开模式把业务入口改为手册锚点；本地 `/guide` 保留真实功能跳转。请勿在此站添加个人数据、登录接口或真实密钥。

## 自动发布

`.github/workflows/pages.yml` 在 main 推送后构建并部署，PR 仅构建不发布。首次需由仓库管理员在 Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**，再手动运行 Public website 工作流，或推送一次相关变更。

在静态预览服务启动后，于 `apps/web` 执行：

```bash
npx playwright test --config playwright.site.config.ts
```

默认测试 `http://127.0.0.1:13003/CareerPilot/`，可用 `SITE_E2E_BASE_URL` 覆盖。测试无需业务服务，覆盖三种屏幕、截图切换、搜索、深层路径与无后端请求。
