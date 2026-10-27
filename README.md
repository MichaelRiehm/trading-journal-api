# Trading Journal API

A REST API where a swing trader plans trades before entering, logs the result, journals thoughts before, during and after each trade, and gets analytics plus a weekly review of habits.

**Status:** Stage 5 (analytics and weekly review). You can register, plan trades, open and close them, journal before, during and after each trade, and get analytics plus a weekly review. Stage 6 is hardening. See [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the full scope and stage plan.

## Endpoints so far

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness |
| GET | `/ready` | none | Readiness (checks the database) |
| POST | `/auth/register` | none | Create an account (JSON: `email`, `password`, 12–128 characters) |
| POST | `/auth/token` | none | OAuth2 password flow (form: `username` = email, `password`); returns a bearer token |
| GET | `/users/me` | bearer | The current user |
| POST, GET | `/strategies` | bearer | Create a strategy; list yours (sorted by name) |
| GET, PATCH, DELETE | `/strategies/{id}` | bearer | Read, rename or delete one (409 while it has trades) |
| POST | `/trades` | bearer | Plan a trade (every trade starts as `planned`) |
| GET | `/trades` | bearer | List, newest first. Filters: `status`, `strategy_id`, `symbol`, `side`, `asset_type`, `source`. Paging: `limit`, `cursor` |
| GET, PATCH, DELETE | `/trades/{id}` | bearer | Read, edit the plan (only while planned) or reassign the strategy, delete |
| POST | `/trades/{id}/open` | bearer | planned → open: record the entry |
| POST | `/trades/{id}/close` | bearer | open → closed: record the exit; the response includes P/L, R-multiple and hold time |
| POST | `/trades/{id}/cancel` | bearer | planned → cancelled |
| POST, GET | `/trades/{id}/journal` | bearer | Add a journal entry (`phase` defaults to the trade's stage, and can't run ahead of it); list them oldest first (`?phase=` filter) |
| PATCH, DELETE | `/journal/{entry_id}` | bearer | Edit or delete an entry |
| GET | `/analytics/summary` | bearer | Win rate, expectancy ($ and R), P/L, fees, hold times, plan adherence, max drawdown. Filters: `start_date`, `end_date` (by close date, UTC), `strategy_id`, `symbol`, `side`, `asset_type`, `source` |
| GET | `/analytics/equity-curve` | bearer | Cumulative P/L after each closed trade (same filters) |
| GET | `/analytics/breakdown?by=` | bearer | The summary per `strategy`, `symbol`, `side`, `asset_type` or `exposure` (same filters) |
| GET | `/analytics/frequency` | bearer | Trades opened per ISO week, empty weeks included (same filters, dates by entry) |
| GET | `/reviews/weekly?week=2026-W42` | bearer | That week's closed and cancelled trades, summary, and journal grouped by phase (defaults to this week) |

Analytics count closed trades only. A breakeven (net P/L of exactly 0) is neither a win nor a loss but counts in every rate; the definitions are in [ADR 0011](docs/decisions/0011-analytics-definitions.md).

Money values are JSON strings (`"98.00000000"`), so they never pass through a float. Another user's ids return 404, and illegal lifecycle moves return 409.

In `/docs`, register, then click **Authorize** and log in with your email as the username.

## Stack

Python 3.15 · FastAPI · Pydantic v2 · SQLAlchemy 2.1 · Alembic · psycopg 3 · PostgreSQL 18 · uv · ruff · mypy · pytest · Docker Compose · GitHub Actions

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker, GNU make.

```sh
uv sync                        # install Python deps into .venv from uv.lock
cp .env.example .env           # local settings (gitignored); then set JWT_SECRET_KEY (see the file)
make up                        # Postgres 18 + the API, waits until healthy
curl http://localhost:8000/health
make down
```

Interactive API docs: http://localhost:8000/docs

## Development

```sh
make db          # start only Postgres (the tests need it)
make migrate     # apply migrations to DATABASE_URL
make test        # pytest (integration tests use a throwaway journal_test database)
make lint        # ruff check + format check
make format      # apply formatting and safe fixes
make typecheck   # mypy --strict
```

Git hooks: `uv tool install pre-commit --python 3.14`, then `pre-commit install`.

## Architecture

Layered: router → service → repository. Details in [CLAUDE.md](CLAUDE.md) and [PROJECT_BRIEF.md](PROJECT_BRIEF.md).

## Decisions

- [0001: Tooling (uv, ruff, mypy, src layout)](docs/decisions/0001-tooling.md)
- [0002: Synchronous database access](docs/decisions/0002-sync-database-access.md)
- [0003: Test database strategy](docs/decisions/0003-test-database-strategy.md)
- [0004: Schema conventions](docs/decisions/0004-schema-conventions.md)
- [0005: Access tokens](docs/decisions/0005-access-tokens.md)
- [0006: Password handling](docs/decisions/0006-password-handling.md)
- [0007: Short positions vs inverse ETFs](docs/decisions/0007-short-vs-inverse-etf.md)
- [0008: Trade lifecycle and derived values](docs/decisions/0008-trade-lifecycle-and-derived-values.md)
- [0009: Keyset pagination](docs/decisions/0009-keyset-pagination.md)
- [0010: Journal phases can't run ahead of the trade](docs/decisions/0010-journal-phase-rules.md)
- [0011: Analytics definitions](docs/decisions/0011-analytics-definitions.md)
- [0012: The weekly review, and recording when a trade was cancelled](docs/decisions/0012-weekly-review-and-cancelled-at.md)

Learning log: [docs/learning-log.md](docs/learning-log.md) · Interview prep: [docs/interview-prep.md](docs/interview-prep.md)
