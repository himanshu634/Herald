# Herald monorepo tasks. Written for GNU Make 3.81 (macOS default): no .ONESHELL.
SERVER := cd apps/server &&
LITE := HERALD_DATABASE_URL=sqlite:///./herald-dev.db HERALD_BUS=memory HERALD_QUEUE=inline
# The API and the arq worker must share one internal token. Dev only: a fixed fallback, so
# make api and make worker agree without setup. Set HERALD_INTERNAL_TOKEN to use your own.
DEV_TOKEN := HERALD_INTERNAL_TOKEN=$${HERALD_INTERNAL_TOKEN:-herald-dev-internal-token-not-secret}
# Run from apps/server. Watch core too: the API imports it, so its edits need a reload.
UVICORN := uv run uvicorn herald_server.api.main:app --port 8000 \
	--reload --reload-dir src --reload-dir ../../packages/core/src

.PHONY: help install infra infra-down dev api worker web lite docker-dev docker-prod docker-prod-down \
	test eval lint format gen-api langfuse langfuse-down

help: ## List tasks
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-17s %s\n", $$1, $$2}'

install: ## Install Python and JS dependencies
	uv sync
	pnpm install

infra: ## Start Postgres and Redis (Docker)
	docker compose -f infra/docker-compose.yml up -d

infra-down: ## Stop Postgres and Redis
	docker compose -f infra/docker-compose.yml down

langfuse: ## Start local Langfuse on :3000 (dev tracing, Docker)
	docker compose -f infra/docker-compose.langfuse.yml up -d --wait

langfuse-down: ## Stop local Langfuse (keeps its data)
	docker compose -f infra/docker-compose.langfuse.yml down

# --wait holds until the healthchecks pass, so the API and worker never start before
# Postgres accepts connections. The API and worker each run create_all on startup; on an
# empty database they race to create the same enum types and one crashes, so create the
# tables once first and their create_all finds nothing to do. Ctrl-C reaches all three
# processes (same process group); the containers keep running, stop them with make infra-down.
dev: ## Start Postgres and Redis (Docker), then the API, worker and web app together
	docker compose -f infra/docker-compose.yml up -d --wait
	$(SERVER) uv run python -c "from sqlmodel import SQLModel, create_engine; \
		import herald_server.models; from herald_server.settings import get_settings; \
		SQLModel.metadata.create_all(create_engine(get_settings().database_url))"
	$(MAKE) -j3 api worker web

api: ## Run the API on :8000 (needs make infra)
	$(SERVER) $(DEV_TOKEN) HERALD_DEBUG=1 $(UVICORN)

worker: ## Run the pipeline worker (needs make infra)
	$(SERVER) $(DEV_TOKEN) uv run arq herald_server.worker.main.WorkerSettings

web: ## Run the web app on :5173 (proxies /api to :8000)
	pnpm -C apps/web dev

lite: ## Run the API with no Docker: SQLite, in-memory bus, inline pipeline
	$(SERVER) $(LITE) HERALD_DEBUG=1 $(UVICORN)

docker-dev: ## Run the full stack in Docker with hot reload (web :5173, API :8000)
	docker compose -f infra/docker-compose.dev.yml up --build

docker-prod: ## Build and start the production stack in Docker (needs .env)
	docker compose --env-file .env -f infra/docker-compose.prod.yml up -d --build

docker-prod-down: ## Stop the production stack (keeps its data)
	docker compose --env-file .env -f infra/docker-compose.prod.yml down

test: ## Run all tests
	uv run pytest
	pnpm -C apps/web test

# ARGS passes options through, e.g. make eval ARGS="--repeats 3" or ARGS="--case sue-is-a-name".
eval: ## Run the triage evals on Claude and write the score report (needs ANTHROPIC_API_KEY)
	uv run herald-evals $(ARGS)

lint: ## Lint, format-check and type-check everything
	uv run ruff check .
	uv run ruff format --check .
	pnpm -C apps/web lint
	pnpm -C apps/web check

format: ## Format everything
	uv run ruff format .
	uv run ruff check --fix .
	pnpm -C apps/web format

gen-api: ## Regenerate web API types from the FastAPI schema
	uv run python -c "import json; from herald_server.api.main import app; print(json.dumps(app.openapi()))" > apps/web/src/lib/api/openapi.json
	pnpm -C apps/web exec openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts
	rm apps/web/src/lib/api/openapi.json
