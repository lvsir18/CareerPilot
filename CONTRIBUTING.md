# 贡献指南

感谢你愿意参与 CareerPilot。这是一个面向个人 / 小团队的求职工作台，**优先保证数据可信与隐私安全**，
所以在接受功能之前会先问两个问题：它是否让岗位信息更可信？它是否会把用户数据带出本机？

## 开始之前

1. 先读 [`README.md`](README.md) 的「快速开始」，把服务跑起来；
2. 二次开发或让 AI 助手接手前，先读 [`AGENTS.md`](AGENTS.md)（代码约定、目录职责、测试要求）；
3. 界面里有一份完整手册：登录后访问 `/guide`，或看 [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)。

## 本地开发

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && ruff format --check .
pytest -q

# 前端
cd apps/web
npm ci --include=optional
npm run lint && npx tsc --noEmit
npx vitest run
```

提交前请确保上面四条命令全部通过。CI 会跑同样的检查（`.github/workflows/ci.yml`）。

## 提交规范

- 分支：`feat/xxx`、`fix/xxx`、`docs/xxx`；
- 提交信息用中文或英文均可，建议 `<type>: <一句话说明>`，例如
  `fix: 岗位方向改为多标签且标题优先`；
- 一个 PR 只做一件事。如果同时修了 bug 和重构，拆成两个 PR 更容易评审；
- **不要提交** `.env`、`backend/.cache/`、任何真实 API Key、真实邮箱或 IP。

## PR 检查清单

- [ ] 新增行为有对应测试（后端 `pytest` / 前端 `vitest`）
- [ ] 涉及数据库变更时附带 Alembic 迁移，并且 `alembic upgrade head` 可重复执行
- [ ] 涉及用户可见行为的，同步更新 `docs/USER_GUIDE.md` 与 `apps/web/lib/guide-content.ts`
- [ ] 没有引入新的外部依赖，除非在 PR 描述里说明必要性
- [ ] 没有把日志、报错信息里的敏感字段（Key、邮箱、Token）打印出来

## 新增一家企业直连支持

这是最受欢迎的一类贡献，流程固定：

1. 在 `backend/app/search/domains.py` 登记官方域名；
2. 如果是 JSON 接口：写一个 connector（参考 `meituan_detail.py`、`tencent_campus.py`）；
   如果是前端渲染站点：在 `backend/app/connectors/official_sources.py` 加一个 `RenderedSourceSpec`；
3. 用 `tools/` 或临时代码验证能拿到：标题、城市、JD、发布时间（有就取，没有就留空）；
4. 补一个 connector 测试，并在 `docs/M2_CHINA_JOB_SOURCES.md` 记录该站点的抓取方式与已知限制。

抓不到 JD 的站点**不要**加进来：候选核验会如实报失败，而不是编造内容。

## 报告问题

用 issue 模板（Bug / Feature）。Bug 请附上：

- 复现步骤与所在页面；
- 服务端日志里的 `request_id`（响应头）或错误码；
- 涉及抓取时，附上目标 URL 与「更新岗位」的结果分类。

## 安全问题

不要开公开 issue，请按 [`SECURITY.md`](SECURITY.md) 的方式私下报告。

## 行为准则

参与本项目即表示同意 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)：保持友善、就事论事、不人身攻击。
