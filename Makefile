SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE ?= docker compose

.PHONY: help env setup dev down logs ps build migrate seed lint test test-backend test-web clean

help: ## 显示可用命令
	@echo "CareerPilot — 常用命令"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "首次使用: make setup && make dev"

env: ## 若不存在则从 .env.example 创建 .env
	@test -f .env || (cp .env.example .env && echo "已从 .env.example 创建 .env")

setup: ## 安装本地开发依赖（Python venv + npm ci）
	@python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || \
		(echo "需要 Python 3.12+，当前为 $$(python3 -V)"; exit 1)
	python3 -m venv backend/.venv
	backend/.venv/bin/python -m pip install --upgrade pip
	backend/.venv/bin/pip install -r backend/requirements-dev.txt
	cd apps/web && npm ci

dev: env ## 构建并启动全部服务（web/api/worker/postgres/redis）
	$(COMPOSE) up --build -d
	@echo ""
	@echo "Web  : http://localhost:$${FRONTEND_PORT:-3000}/login"
	@echo "API  : http://localhost:$${BACKEND_PORT:-8000}/healthz"
	@echo "Docs : http://localhost:$${BACKEND_PORT:-8000}/docs"
	@echo "下一步: make migrate && make seed"
	@echo "日志 : make logs"

down: ## 停止并移除容器（保留数据卷）
	$(COMPOSE) down

logs: ## 跟踪查看所有服务日志
	$(COMPOSE) logs -f --tail=100

ps: ## 查看服务健康状态
	$(COMPOSE) ps

build: ## 重新构建镜像
	$(COMPOSE) build

migrate: env ## 应用 Alembic 迁移（需要先构建镜像）
	$(COMPOSE) up -d --wait postgres
	$(COMPOSE) run --rm --no-deps api alembic upgrade head

seed: migrate ## 导入明确标注的 Demo 岗位（幂等，生产拒绝执行）
	$(COMPOSE) run --rm --no-deps api python -m app.db.seed

lint: ## 后端 ruff + 前端 eslint/typecheck
	@test -x backend/.venv/bin/ruff || (echo "缺少 backend/.venv，请先运行 make setup"; exit 1)
	cd backend && .venv/bin/ruff check .
	cd backend && .venv/bin/ruff format --check .
	cd apps/web && npm run lint
	cd apps/web && npm run typecheck

test: test-backend test-web ## 运行全部单元/集成测试

test-backend: ## 后端 pytest（需要 PostgreSQL）
	@test -x backend/.venv/bin/python || (echo "缺少 backend/.venv，请先运行 make setup"; exit 1)
	@$(COMPOSE) ps --status running --services 2>/dev/null | grep -qx postgres || \
		(echo "需要 PostgreSQL：运行 docker compose up -d --wait postgres"; exit 1)
	cd backend && .venv/bin/python -m pytest

test-web: ## 前端 vitest
	cd apps/web && npm test

clean: ## 删除本地构建产物（不动 Docker 数据卷）
	rm -rf apps/web/.next apps/web/coverage backend/.pytest_cache backend/.ruff_cache

e2e: ## 运行 Playwright 浏览器端到端测试（需先启动服务）
	cd apps/web && npx playwright test

smoke: ## 可选：真实外部服务冒烟（Tavily / QQ IMAP / Gmail / LLM）
	@echo "外部冒烟测试需显式配置外部凭据；按需手动执行对应脚本。"
