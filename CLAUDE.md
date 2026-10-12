# CLAUDE.md

Short working guide. `PROJECT_BRIEF.md` is the source of truth and the long reference; read it before starting a stage.

## What this is

A REST API for a swing trader: plan a trade, open and close it, journal before/during/after, and get analytics plus a weekly review. Python 3.15, FastAPI, Pydantic v2, SQLAlchemy 2.1, Alembic, psycopg 3, PostgreSQL 18. A portfolio project: every decision must be one Michael can explain and defend.

## Architecture

Layered: **router → service → repository**.
- **Routers** (`src/trading_journal/api/`): HTTP only. Validate with Pydantic schemas, call a service, map domain errors to status codes.
- **Services**: business rules (state transitions, ownership, P/L and R math). No FastAPI imports.
- **Repositories**: all SQLAlchemy queries. No business rules.
- Pydantic schemas (Create / Update / Read per resource) are separate from ORM models.
- Analytics math lives in pure functions with unit tests that don't need a database.

## Domain rules that are easy to get wrong

- Money, prices, quantities: `Decimal` in Python, `NUMERIC` in Postgres. **Never float.**
- Every row belongs to a user. Another user's data returns **404, not 403**.
- Lifecycle: `planned → open → closed`, `planned → cancelled`. Illegal transitions return **409**.
- Derived values (P/L, R-multiple, hold time) are computed, never accepted from the client.

## Working rules

- Every change: GitHub issue → branch `<issue>-short-name` → PR → CI green → AI review → Michael reviews and merges. Nothing reaches `main` without Michael.
- Small commits, conventional commit messages (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).
- Start each stage in plan mode and wait for approval before writing code.
- No new dependency without a reason stated in the PR.
- One ADR per real choice in `docs/decisions/NNNN-title.md` (Context, Decision, Alternatives considered, Consequences). Claude drafts; Michael rewrites.
- After each stage: explain what was built and the main Python concepts for a C#/.NET developer, and append a stub to `docs/learning-log.md`.

## Commands

```sh
uv sync                  # create .venv and install exactly what uv.lock pins
make up                  # build + start Postgres and the API (needs .env; copy .env.example)
make down                # stop containers, keep the database volume
make test                # uv run pytest
make lint                # ruff check + ruff format --check
make format              # ruff format + ruff check --fix
make typecheck           # uv run mypy (strict)
uv run uvicorn trading_journal.main:app --reload   # run the API on the host
uv add <pkg>             # add a runtime dependency (uv add --dev <pkg> for dev-only)
pre-commit run --all-files
```

pre-commit is installed as a uv tool on Python 3.14 (`uv tool install pre-commit --python 3.14`), because PyYAML has no 3.15 wheel yet. See `docs/decisions/0001-tooling.md`.
