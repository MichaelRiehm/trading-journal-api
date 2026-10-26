# Recipes stay one plain command per line so they run the same under sh (CI, Linux)
# and cmd.exe (GNU make on Windows).

.PHONY: up down db migrate test lint format typecheck

up: ## Build the image, start Postgres, run migrations, start the API; wait until healthy
	docker compose up --build --detach --wait

down: ## Stop the containers (the database volume is kept)
	docker compose down

db: ## Start only Postgres (enough for tests and for running the API on the host)
	docker compose up --detach --wait db

migrate: ## Apply migrations to DATABASE_URL
	uv run alembic upgrade head

test: ## Run the test suite (needs Postgres: `make db`)
	uv run pytest

lint: ## Lint and check formatting without changing files
	uv run ruff check .
	uv run ruff format --check .

format: ## Format and apply safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Static type check (mypy strict)
	uv run mypy
