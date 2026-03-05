SHELL := /bin/bash

.DEFAULT_GOAL := help

-include .worktree.env

COMPOSE_PROJECT_NAME ?= orchestrator
WORKER_IMAGE ?= orchestrator-worker:latest
ORCHESTRATOR_FRONTEND_PORT ?= 13000
ORCHESTRATOR_BACKEND_PORT ?= 18000
DOCKER_COMPOSE := COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) \
  WORKER_IMAGE=$(WORKER_IMAGE) \
  ORCHESTRATOR_FRONTEND_PORT=$(ORCHESTRATOR_FRONTEND_PORT) \
  ORCHESTRATOR_BACKEND_PORT=$(ORCHESTRATOR_BACKEND_PORT) \
  docker compose
HEALTHCHECK_RETRIES ?= 60
HEALTHCHECK_INTERVAL ?= 2

.PHONY: \
	help \
	up down restart build build-worker ps ports-info logs logs-backend logs-frontend logs-db \
	shell-backend shell-frontend shell-db gh-login \
	backend-install backend-test backend-lint backend-check backend-migrate backend-migrate-head \
	frontend-install frontend-lint frontend-build frontend-check \
	e2e-install e2e-install-browser e2e-prepare-ci e2e-up e2e-down wait-backend wait-frontend e2e-test \
	ci-unit ci-e2e \
	check clean

help: ## Show available commands
	@echo "Orchestrator Make Commands"
	@echo ""
	@echo "Docker:"
	@echo "  make up                    Start containers in detached mode (build included)"
	@echo "  make down                  Stop and remove containers"
	@echo "  make restart               Restart containers"
	@echo "  make build                 Build images"
	@echo "  make build-worker          Build task worker Docker image"
	@echo "  make ps                    Show compose service status"
	@echo "  make ports-info            Show service URLs"
	@echo "  make logs                  Follow all service logs"
	@echo "  make logs-backend          Follow backend logs"
	@echo "  make logs-frontend         Follow frontend logs"
	@echo "  make logs-db               Follow database logs"
	@echo "  make shell-backend         Open shell in backend container"
	@echo "  make shell-frontend        Open shell in frontend container"
	@echo "  make shell-db              Open psql shell in db container"
	@echo "  make gh-login              Run gh auth login inside backend container"
	@echo ""
	@echo "Backend (local):"
	@echo "  make backend-install       Install backend deps with uv"
	@echo "  make backend-test          Run backend pytest suite"
	@echo "  make backend-lint          Run backend ruff checks"
	@echo "  make backend-check         Run backend lint + tests"
	@echo "  make backend-migrate-head  Run alembic upgrade head"
	@echo "  make backend-migrate MSG=  Create a new alembic revision"
	@echo ""
	@echo "Frontend (local):"
	@echo "  make frontend-install      Install frontend npm deps"
	@echo "  make frontend-lint         Run frontend lint"
	@echo "  make frontend-build        Run frontend production build"
	@echo "  make frontend-check        Run frontend lint + build"
	@echo ""
	@echo "Project:"
	@echo "  make check                 Run backend-check + frontend-check"
	@echo "  make ci-unit               Run backend + frontend CI unit checks"
	@echo "  make ci-e2e                Run e2e tests against docker compose services"
	@echo "  make e2e-prepare-ci        Install e2e deps + Playwright browser (CI mode)"
	@echo "  make e2e-up                Start e2e docker services"
	@echo "  make e2e-down              Stop e2e docker services and remove volumes"
	@echo "  make e2e-test              Run Playwright e2e suite"
	@echo "  make clean                 Remove local build/runtime caches"
	@echo ""
	@echo "Port overrides:"
	@echo "  ORCHESTRATOR_FRONTEND_PORT=3000 ORCHESTRATOR_BACKEND_PORT=8000 make up"

up: build-worker ## Start containers in detached mode with build
	@$(DOCKER_COMPOSE) up -d --build

down: ## Stop and remove containers
	@$(DOCKER_COMPOSE) down

restart: ## Restart compose services
	@$(DOCKER_COMPOSE) restart

build: build-worker ## Build compose images
	@$(DOCKER_COMPOSE) build

build-worker: ## Build the task worker Docker image
	@docker build -t $(WORKER_IMAGE) worker/

ps: ## Show service status
	@$(DOCKER_COMPOSE) ps

ports-info: ## Show service URLs
	@echo "Frontend: http://localhost:$(ORCHESTRATOR_FRONTEND_PORT)"
	@echo "Backend:  http://localhost:$(ORCHESTRATOR_BACKEND_PORT)"
	@echo "API docs: http://localhost:$(ORCHESTRATOR_BACKEND_PORT)/docs"

logs: ## Follow all service logs
	@$(DOCKER_COMPOSE) logs -f

logs-backend: ## Follow backend logs
	@$(DOCKER_COMPOSE) logs -f backend

logs-frontend: ## Follow frontend logs
	@$(DOCKER_COMPOSE) logs -f frontend

logs-db: ## Follow db logs
	@$(DOCKER_COMPOSE) logs -f db

shell-backend: ## Open shell inside backend container
	@$(DOCKER_COMPOSE) exec backend bash

shell-frontend: ## Open shell inside frontend container
	@$(DOCKER_COMPOSE) exec frontend bash

shell-db: ## Open psql shell inside db container
	@$(DOCKER_COMPOSE) exec db psql -U postgres -d orchestrator

gh-login: ## Authenticate gh CLI in backend container
	@$(DOCKER_COMPOSE) exec backend gh auth login

backend-install: ## Install backend dependencies with uv
	@cd backend && uv sync --extra dev

backend-test: ## Run backend tests
	@cd backend && .venv/bin/pytest -q

backend-lint: ## Run backend lint checks
	@cd backend && .venv/bin/ruff check

backend-check: backend-lint backend-test ## Run backend lint and tests

backend-migrate-head: ## Apply latest alembic migrations
	@cd backend && .venv/bin/alembic upgrade head

backend-migrate: ## Create a new alembic revision: make backend-migrate MSG="add table"
	@if [ -z "$(MSG)" ]; then echo "MSG is required (example: make backend-migrate MSG='add table')"; exit 1; fi
	@cd backend && .venv/bin/alembic revision -m "$(MSG)"

frontend-install: ## Install frontend dependencies
	@cd frontend && npm install

frontend-lint: ## Run frontend lint
	@cd frontend && npm run lint

frontend-build: ## Run frontend production build
	@cd frontend && npm run build

frontend-check: frontend-lint frontend-build ## Run frontend lint and build

e2e-install: ## Install e2e dependencies
	@cd e2e && npm ci

e2e-install-browser: ## Install Playwright browser for local e2e runs
	@cd e2e && npx playwright install chromium

e2e-prepare-ci: e2e-install ## Install e2e deps and CI browser dependencies
	@cd e2e && npx playwright install --with-deps chromium

e2e-up: ## Start e2e services with docker compose
	@$(DOCKER_COMPOSE) up -d --build

e2e-down: ## Stop e2e services and remove volumes
	@$(DOCKER_COMPOSE) down -v --remove-orphans

wait-backend: ## Wait until backend health endpoint is ready
	@for attempt in $$(seq 1 $(HEALTHCHECK_RETRIES)); do \
		if curl -fsS --max-time 5 "http://localhost:$(ORCHESTRATOR_BACKEND_PORT)/healthz" >/dev/null; then \
			echo "Backend is ready"; \
			exit 0; \
		fi; \
		sleep $(HEALTHCHECK_INTERVAL); \
	done; \
	echo "Backend failed readiness check"; \
	exit 1

wait-frontend: ## Wait until frontend endpoint is ready
	@for attempt in $$(seq 1 $(HEALTHCHECK_RETRIES)); do \
		if curl -fsS --max-time 5 "http://localhost:$(ORCHESTRATOR_FRONTEND_PORT)" >/dev/null; then \
			echo "Frontend is ready"; \
			exit 0; \
		fi; \
		sleep $(HEALTHCHECK_INTERVAL); \
	done; \
	echo "Frontend failed readiness check"; \
	exit 1

e2e-test: ## Run Playwright e2e tests
	@cd e2e && npm run test

ci-unit: backend-install backend-check frontend-install frontend-check ## Run CI unit checks

ci-e2e: e2e-up wait-backend wait-frontend e2e-test ## Run CI e2e checks against compose services

check: backend-check frontend-check ## Run all local checks

clean: ## Remove local caches and generated artifacts
	@rm -rf backend/.pytest_cache backend/.ruff_cache frontend/.next e2e/playwright-report e2e/test-results
