.PHONY: setup db migrate seed api web test lint data benchmarks

setup:  ## Install backend and web dependencies
	cd backend && uv sync
	cd web && pnpm install

db:  ## Start Postgres in Docker
	docker compose up -d db

migrate:  ## Apply database migrations
	cd backend && uv run alembic upgrade head

seed:  ## Load reference benchmarks, demo data and estimates
	cd backend && uv run chorizo seed-reference && uv run chorizo seed-demo && uv run chorizo refresh-estimates

api:  ## Run the API on :8000
	cd backend && uv run uvicorn chorizo.api.main:app --reload --port 8000

web:  ## Run the web app on :3000
	cd web && pnpm dev

test:  ## Run all tests and checks
	cd backend && uv run ruff check . && uv run pytest -q
	cd web && pnpm lint && pnpm build

data:  ## Import ClinicalTrials.gov, build programs, recompute benchmarks and estimates
	cd backend && uv run chorizo refresh-data $(if $(PAGES),--max-pages $(PAGES))

benchmarks:  ## Rebuild programs, benchmarks and estimates from already-imported trials
	cd backend && uv run chorizo build-programs && uv run chorizo compute-benchmarks && uv run chorizo refresh-estimates
