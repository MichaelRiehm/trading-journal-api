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
- Protected routes take `user: CurrentUser` (`api/deps.py`) and pass `user.id` into scoped repository queries. Services raise errors from `domain/errors.py`; `api/errors.py` maps them to HTTP status codes.
- Trade rules live in `domain/`: `lifecycle.py` (transition table), `calculations.py` (Decimal math, reused by analytics), `trade_rules.py` (plan validation), `journal_rules.py` (which phases a trade's status allows). Request models extend `schemas/base.RequestModel` (unknown fields → 422).- API tests use the `api_client` fixture (requests share the test's rolled-back session) and the helpers in `tests/api_helpers.py`.

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
- **Progress first, learning later.** Michael's touchpoints per stage: approve the plan, merge the PR. Make decisions and recommend them; don't ask open questions.
- One ADR per real choice in `docs/decisions/NNNN-title.md` (Context, Decision, Alternatives considered, Consequences). Claude writes them in full. They are append-only: supersede a decision, don't rewrite it.
- End of each stage:
  - write the stage's entry in `docs/learning-log.md` (marked as not yet reviewed by Michael)
  - add its decisions, concepts and likely interview questions to `docs/interview-prep.md`
  - give a brief explanation of the main Python concepts for a C#/.NET developer

## Commands

```sh
uv sync                  # create .venv and install exactly what uv.lock pins
make up                  # build + start Postgres and the API (needs .env; copy .env.example)
make down                # stop containers, keep the database volume
make db                  # start only Postgres
make migrate             # alembic upgrade head
make test                # uv run pytest (needs `make db`; uses a throwaway journal_test database)
uv run alembic revision --autogenerate -m "..."   # new migration: always review the file
make lint                # ruff check + ruff format --check
make format              # ruff format + ruff check --fix
make typecheck           # uv run mypy (strict)
uv run uvicorn trading_journal.main:app --reload   # run the API on the host
uv add <pkg>             # add a runtime dependency (uv add --dev <pkg> for dev-only)
pre-commit run --all-files
```

pre-commit is installed as a uv tool on Python 3.14 (`uv tool install pre-commit --python 3.14`), because PyYAML has no 3.15 wheel yet. See `docs/decisions/0001-tooling.md`.
