# Trading Journal API

A REST API for a swing trader:
- **plan** a trade before entering it
- **open and close** it
- **journal** your thinking before, during and after
- get **analytics** and a **weekly review** of your habits

It's built as a portfolio project: production-shaped, tested, and with every real decision written down as an ADR.

Python 3.15 · FastAPI · Pydantic v2 · SQLAlchemy 2.1 · Alembic · psycopg 3 · PostgreSQL 18 · uv · ruff · mypy (strict) · pytest · Docker · GitHub Actions

**Status:** Phase 1 is complete: Stages 0–6 of [PROJECT_BRIEF.md](PROJECT_BRIEF.md).

## Features

- **Accounts:**
  - register, then log in with the OAuth2 password flow to get a JWT bearer token
  - every row belongs to one user
  - another user's data returns 404, never 403
- **The trade lifecycle:** `planned → open → closed`, or `planned → cancelled`.
  - Illegal moves return 409.
  - The plan (entry, stop, target, thesis) is locked once the trade opens, so analytics can measure against it.
- **Derived values are computed, never accepted:** P/L, R-multiple, hold time and exposure. Long positions in inverse ETFs count as bearish ([ADR 0007](docs/decisions/0007-short-vs-inverse-etf.md)).
- **Journal entries** per trade, in `pre`, `during` and `post` phases.
  - A phase can't run ahead of the trade.
  - Earlier phases can be backfilled.
- **Analytics** over closed trades:
  - win rate
  - expectancy in $ and R
  - P/L, fees, the largest win and loss
  - hold times
  - plan adherence
  - max drawdown
  - an equity curve
  - breakdowns by strategy, symbol, side, asset type or exposure
  - trades opened per week
- **A weekly review** (`?week=2026-W42`): the week's closed and cancelled trades, its numbers, and every journal entry grouped by phase.

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker, GNU make.

```sh
uv sync                    # install the locked dependencies into .venv
cp .env.example .env       # local settings (gitignored); set JWT_SECRET_KEY as the file explains
make up                    # build the image; start Postgres, run migrations, start the API
curl http://127.0.0.1:8000/health
make down                  # stop (the database volume is kept)
```

Interactive docs: http://127.0.0.1:8000/docs. Register there, click **Authorize**, and log in with your email as the username.

Without Docker for the API (Postgres still in Docker):

```sh
make db && make migrate
uv run uvicorn trading_journal.main:app --reload
```

## Configuration

These are environment variables, read from `.env` when present. [.env.example](.env.example) documents each one.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pw@127.0.0.1:5432/journal` |
| `JWT_SECRET_KEY` | yes (API) | | At least 32 characters; signs access tokens (HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `60` | Token lifetime. There are no refresh tokens |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `TEST_DATABASE_URL` | no | `DATABASE_URL` + `_test` | The throwaway database the tests create and drop |
| `POSTGRES_*`, `API_PORT` | compose | see `.env.example` | The compose database and host ports (bound to 127.0.0.1) |

Bad or missing settings stop the API at startup, and a rejected secret is never echoed in the error.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness |
| GET | `/ready` | none | Readiness (checks the database; 503 if it's down) |
| POST | `/auth/register` | none | Create an account (JSON: `email`, `password` of 12–128 characters) |
| POST | `/auth/token` | none | OAuth2 password flow (form: `username` = email, `password`); returns a bearer token |
| GET | `/users/me` | bearer | The current user |
| POST, GET | `/strategies` | bearer | Create a strategy; list yours (by name) |
| GET, PATCH, DELETE | `/strategies/{id}` | bearer | Read, rename or delete one (409 while it has trades) |
| POST | `/trades` | bearer | Plan a trade (every trade starts as `planned`) |
| GET | `/trades` | bearer | Newest first, paginated. Filters: `status`, `strategy_id`, `symbol`, `side`, `asset_type`, `source` |
| GET, PATCH, DELETE | `/trades/{id}` | bearer | Read; edit the plan (only while planned) or reassign the strategy; delete |
| POST | `/trades/{id}/open` | bearer | planned → open: record the entry |
| POST | `/trades/{id}/close` | bearer | open → closed: record the exit. The response includes P/L, R and hold time |
| POST | `/trades/{id}/cancel` | bearer | planned → cancelled |
| POST, GET | `/trades/{id}/journal` | bearer | Add an entry (`phase` defaults to the trade's stage); list them oldest first (`?phase=`) |
| PATCH, DELETE | `/journal/{entry_id}` | bearer | Edit or delete an entry |
| GET | `/analytics/summary` | bearer | The metrics above. Filters: `start_date`, `end_date` (close date, UTC, inclusive), `strategy_id`, `symbol`, `side`, `asset_type`, `source` |
| GET | `/analytics/equity-curve` | bearer | Cumulative P/L after each closed trade (same filters) |
| GET | `/analytics/breakdown?by=` | bearer | The summary per `strategy`, `symbol`, `side`, `asset_type` or `exposure` |
| GET | `/analytics/frequency` | bearer | Trades opened per ISO week, empty weeks included (dates filter on entry) |
| GET | `/reviews/weekly?week=2026-W42` | bearer | One ISO week's closed and cancelled trades, summary and journal (defaults to this week) |

Analytics count closed trades only. A breakeven (net P/L of exactly 0) is neither a win nor a loss, but it counts in every rate. Every definition is in [ADR 0011](docs/decisions/0011-analytics-definitions.md).

## API conventions

- **Money, prices and quantities** are `Decimal` in Python and `NUMERIC(20, 8)` in Postgres. In JSON they are fixed-point **strings** (`"98.00000000"`), so they never pass through a float. Rates are fractions (`"0.6667"`), and R-multiples have 4 decimal places.
- **Times** are ISO 8601 in UTC; inputs with an offset are converted. Durations are ISO 8601 (`"P4DT5H30M"`). Weeks are ISO weeks in UTC.
- **Unknown fields** in a request body are a 422, so a typo in a PATCH is rejected instead of being silently ignored.
- **Errors are [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details** (`application/problem+json`), for every status, documented in OpenAPI ([ADR 0013](docs/decisions/0013-error-responses-and-pagination.md)):

  ```json
  {"type": "about:blank", "title": "Conflict", "status": 409,
   "detail": "Cannot close a trade that is planned",
   "instance": "/trades/01a1…/close", "request_id": "03c0dc89cb9b48cfbb00eea0c08b37f7"}
  ```

  - **What each status means here:**
    - 401: a missing or invalid token. It includes `WWW-Authenticate: Bearer`.
    - 404: not found, or not yours.
    - 409: the request conflicts with the current state, for example an illegal lifecycle move or a duplicate.
    - 422: invalid input.
  - **Request-validation 422s add `errors: [{loc, msg, type}]`.** The rejected value is never echoed back.
  - **A 500 says only "Internal server error",** plus the request id to look up in the logs.
- **Pagination:**
  - **Collections that grow without bound** (`/trades`) return `{"items": [...], "next_cursor": ...}`. Pass `next_cursor` back as `cursor` for the next page; `limit` is 1–200 (default 50). This is keyset pagination on the time-ordered UUIDv7 id ([ADR 0009](docs/decisions/0009-keyset-pagination.md)).
  - **Small, bounded collections** return a plain array.
- **Request ids:** every response has an `X-Request-ID` header. Send your own (1–64 characters of `A-Z a-z 0-9 . _ -`) to trace a request end to end.

## Architecture

```
HTTP ─▶ middleware (request id, access log, last-resort 500)
     ─▶ api/        routers: HTTP only. Pydantic validation, auth dependency, status codes
     ─▶ services/   business rules: ownership, lifecycle, the transaction (commit/rollback)
     ─▶ repositories/  every SQLAlchemy query, always scoped by user_id
     ─▶ PostgreSQL  CHECK constraints make illegal rows unstorable, even if a service has a bug

domain/   pure Python with no I/O: the lifecycle table, journal rules, Decimal trade math,
          analytics metrics, ISO weeks. Unit-tested without a database.
schemas/  Pydantic request and response models, separate from the ORM models (models/)
```

- **Services raise domain errors** (`domain/errors.py`), and `api/errors.py` maps them to problem responses. Services never import FastAPI.
- **Database access is synchronous** ([ADR 0002](docs/decisions/0002-sync-database-access.md)): FastAPI runs sync routes in a thread pool.
- **The project layout:**

  ```
  src/trading_journal/
    api/            routers, dependencies (deps.py), errors.py, middleware.py
    domain/         lifecycle, trade_rules, journal_rules, calculations, analytics, iso_week
    services/  repositories/  schemas/  models/  db/
    config.py       settings (pydantic-settings)
    logging_config.py   JSON logging
    security.py     password hashing (Argon2id) and JWTs
  migrations/       Alembic (hand-reviewed; CHECK constraints are hand-written)
  tests/            unit and integration tests
  docs/decisions/   ADRs
  ```

## Testing

```sh
make db          # Postgres must be running
make test        # pytest: about 330 tests, about 30 s
make lint        # ruff check + ruff format --check
make typecheck   # mypy --strict
```

- **The database tests** run against real PostgreSQL. A throwaway `journal_test` database is created and migrated once, and each test runs inside a transaction that is rolled back ([ADR 0003](docs/decisions/0003-test-database-strategy.md)).
- **What the suite covers:**
  - API tests drive the real app through FastAPI's `TestClient`.
  - The analytics and lifecycle math have database-free unit tests.
  - Ownership is checked endpoint by endpoint.
  - Migrations run upgrade, downgrade and upgrade again, plus a backfill test.
  - The OpenAPI document is checked to describe every error.
  - The logs are checked to contain no secrets.
- **CI** (GitHub Actions) runs lint, type check and tests against Postgres 18. A second job builds the Docker image and checks that it runs as non-root and stays under 300 MB.
- **Git hooks:** `uv tool install pre-commit --python 3.14`, then `pre-commit install`. pre-commit runs on 3.14 until PyYAML ships 3.15 wheels; see ADR 0001.

## Logging

Logs are JSON lines on stdout ([ADR 0014](docs/decisions/0014-structured-logging.md)), one access line per request:

```json
{"timestamp": "2026-10-27T14:57:14.636+00:00", "level": "INFO", "logger": "trading_journal.request",
 "message": "request", "request_id": "03c0…", "user_id": "01a1…", "method": "POST",
 "path": "/trades/01a1…/close", "status": 409, "duration_ms": 4.3}
```

- **What is never logged:** headers, bodies, query strings, or SQL parameters (`hide_parameters=True`). So no passwords, hashes or tokens.
- **An unhandled error** is logged once, with its traceback and the request id that the client got in the 500.
- **Reading them:** `docker compose logs api | jq`.

## Docker image

- **The base:** multi-stage on the official `python:3.15.0-slim-trixie` ([ADR 0015](docs/decisions/0015-runtime-image.md)). The runtime stage holds only the base image and the locked virtualenv.
- **Security:** it runs as a non-root user.
- **Health:** it has a `HEALTHCHECK`.
- **Size:** about 290 MB, down from 412 MB in Stage 0.
- **Migrations:** the same image runs them (`alembic upgrade head`, the compose `migrate` service).

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
- [0013: Error responses (RFC 9457) and pagination conventions](docs/decisions/0013-error-responses-and-pagination.md)
- [0014: Structured logging and request ids](docs/decisions/0014-structured-logging.md)
- [0015: The runtime image on the official Python base](docs/decisions/0015-runtime-image.md)

How it was built: [docs/learning-log.md](docs/learning-log.md) (one entry per stage) · [docs/interview-prep.md](docs/interview-prep.md) (decisions and likely questions) · working guide: [CLAUDE.md](CLAUDE.md)
