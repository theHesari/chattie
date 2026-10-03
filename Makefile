COMPOSE  := docker-compose
PROFILES := --profile prod --profile dev --profile langfuse

.PHONY: help build prod dev stack dev-stack down clean logs ps shell health

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the chattie image
	$(COMPOSE) build

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
