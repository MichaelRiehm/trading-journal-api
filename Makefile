# Recipes stay one plain command per line so they run the same under sh (CI, Linux)
# and cmd.exe (GNU make on Windows).

.PHONY: up down test lint format typecheck

up: ## Build the API image, start Postgres and the API, wait until both are healthy
	docker compose up --build --detach --wait

down: ## Stop the containers (the database volume is kept)
	docker compose down

test: ## Run the test suite
	uv run pytest

lint: ## Lint and check formatting without changing files
	uv run ruff check .
	uv run ruff format --check .

format: ## Format and apply safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Static type check (mypy strict)
	uv run mypy
