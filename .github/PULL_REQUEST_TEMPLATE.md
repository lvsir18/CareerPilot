## 这个 PR 做了什么

<!-- 一句话说明；如果修了 bug，写清触发条件 -->

## 关联 issue

<!-- Closes #123 -->

## 验证方式

<!-- 你实际跑过什么，而不是「应该能通过」 -->

- [ ] `cd backend && ruff check . && ruff format --check . && pytest -q`
- [ ] `cd apps/web && npm run lint && npx tsc --noEmit && npx vitest run`
- [ ] 涉及界面时，手动点过相关页面（说明机型 / 视口）

## 检查清单

- [ ] 新增行为有测试覆盖
- [ ] 有数据库变更时附带 Alembic 迁移，`alembic upgrade head` 可重复执行
- [ ] 用户可见行为变化时，更新了 `docs/USER_GUIDE.md` 与 `apps/web/lib/guide-content.ts`
- [ ] 没有提交 `.env`、真实 Key、真实邮箱或 IP
- [ ] 抓取类改动注明：目标站点、抓到的字段、已知限制（例如「虚拟列表只能取首屏 10 条」）

## 截图 / 录屏（涉及界面时）

<!-- 请使用脱敏后的数据 -->
