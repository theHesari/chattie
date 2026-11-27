COMPOSE  := docker-compose
PROFILES := --profile prod --profile dev --profile langfuse

.PHONY: help build prod dev stack dev-stack down clean logs ps shell health web-install web web-lint test-api web-migrate db-world db-extend db-dump db-restore invite db-backup archive-inactive api-recreate db-migrate

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the chattie images (prod + dev)
	$(COMPOSE) $(PROFILES) build

prod: ## Start chattie only (production mode on :8000)
	$(COMPOSE) --profile prod up -d

dev: ## Start chattie only (dev mode: reload + bind-mount)
	$(COMPOSE) --profile dev up

stack: ## Start chattie (prod) + full Langfuse stack
	$(COMPOSE) --profile prod --profile langfuse up -d

dev-stack: ## Start chattie (dev) + full Langfuse stack
	$(COMPOSE) --profile dev --profile langfuse up

down: ## Stop everything (keeps volumes)
	$(COMPOSE) $(PROFILES) down

clean: ## Stop everything + delete volumes (destructive)
	$(COMPOSE) $(PROFILES) down -v

logs: ## Tail logs from everything that's running
	$(COMPOSE) logs -f --tail=100

ps: ## Show running containers
	$(COMPOSE) ps

shell: ## Open a shell inside the running chattie container
	$(COMPOSE) exec chattie bash || $(COMPOSE) exec chattie-dev bash

health: ## Hit chattie's /health endpoint
	@curl -s http://localhost:8000/health | python3 -m json.tool

web-install: ## Install web UI dependencies (npm workspaces)
	npm install

web: ## Start the web UI dev server on :3001 (Langfuse owns :3000)
	npm run dev -w @chattie/web

web-lint: ## Type-check and lint the web UI
	cd apps/web && npx tsc --noEmit && npm run lint

web-migrate: ## Create/upgrade Better Auth tables (auth schema of the chattie DB)
	cd apps/web && set -a && . ./.env.local && set +a && npx auth@latest migrate --config lib/auth.ts -y

test-api: ## Run the backend tests against the local Postgres (throwaway test database)
	cd services/llm && ../../venv/bin/pytest tests

db-migrate: ## Create roles and apply pending SQL migrations to DB_NAME (never drops data)
	cd services/llm && ../../venv/bin/python -m db.migrate

db-world: ## Build the company world: make db-world AS_OF=2026-11-27 [WORLD_ARGS="--reset --confirm"]
	cd services/llm && ../../venv/bin/python -m db.company.setup world --as-of $(AS_OF) $(WORLD_ARGS)

db-extend: ## Append orders and work days up to a date: make db-extend TO=2026-12-31
	cd services/llm && ../../venv/bin/python -m db.company.setup extend --to $(TO)

db-dump: ## Write the seeded world (no generated characters) to services/llm/db/company/dump/world.dump
	cd services/llm && ../../venv/bin/python -m db.company.setup dump

db-restore: ## Load the dump into DB_NAME (add RESTORE_ARGS=--confirm to replace an existing world)
	cd services/llm && ../../venv/bin/python -m db.company.setup restore $(RESTORE_ARGS)

invite: ## Issue a sign-up invite code: make invite [EMAIL=person@example.com] [DAYS=14]
	cd services/llm && ../../venv/bin/python -m db.invites create $(if $(EMAIL),--email $(EMAIL)) $(if $(DAYS),--days $(DAYS))

db-backup: ## Back up DB_NAME to a verified pg_dump file: make db-backup [BACKUP_PATH=file]
	cd services/llm && ../../venv/bin/python -m db.backup $(BACKUP_PATH)

archive-inactive: ## Archive characters inactive for more than 30 days (run daily): make archive-inactive [DAYS=30]
	cd services/llm && ../../venv/bin/python -m db.company.setup archive $(if $(DAYS),--days $(DAYS))

api-recreate: ## Recreate only the dev API container so it reloads .env (no build; leaves Langfuse running)
	$(COMPOSE) --profile dev --profile langfuse up -d --no-build --no-deps --force-recreate chattie-dev
