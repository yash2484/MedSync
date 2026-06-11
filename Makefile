.PHONY: up down build logs migrate test seed fmt

up:            ## Start the full stack
	docker compose up -d --build

down:          ## Stop the stack
	docker compose down

build:         ## Rebuild images
	docker compose build

logs:          ## Tail api + worker logs
	docker compose logs -f api worker

reload:        ## Fast restart after code changes (no rebuild; source is bind-mounted)
	docker compose restart api worker

ps:            ## Show service status
	docker compose ps

migrate:       ## Apply DB migrations
	docker compose exec api uv run alembic upgrade head

test:          ## Run the test suite (inside the api container)
	docker compose exec api uv run pytest -q

seed:          ## Load dev fixtures + (Phase 2) ESI guidelines
	@echo "seed: implemented in Increment 1+"

fmt:           ## Lint/format
	cd server && uv run ruff check --fix . && uv run ruff format .
