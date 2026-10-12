# Trading Journal API: Project Brief

Source of truth for the product and the working rules. Claude Code reads this first. Owner: Michael.

## Goal

A portfolio project that closes three skill gaps for Japan backend and platform roles: Python (production service), Kubernetes, and AWS infrastructure. Every decision must be one the owner understands and can defend in an interview. Depth over breadth. Accuracy over embellishment.

## Product (v1)

A REST API where a swing trader plans trades before entering, logs the result, journals thoughts before, during and after, and gets analytics plus a weekly review of habits.

### Trade lifecycle

```
planned -> open -> closed
planned -> cancelled
```

- **planned**: created with a required plan (planned entry, stop, target, thesis). Nothing has happened yet.
- **open**: actual entry recorded (price, quantity, time).
- **closed**: actual exit recorded (price, time, fees). Analytics only count closed trades.
- **cancelled**: plan never taken. Kept, because skipped setups are useful in reviews.
- Illegal transitions (closing a planned trade, reopening a closed one) return 409.

Single entry and single exit per trade. The owner goes all in and all out on swing trades, so fills and scaling are out of scope.

### Entities

| Entity | Key fields |
|---|---|
| User | id, email, password hash, created_at |
| Strategy | id, user_id, name, description. Names unique per user |
| Trade | id, user_id, strategy_id, symbol, asset_type (stock, etf, crypto), leverage_factor (optional: 2, 3, -2, -3 for leveraged and inverse ETFs), side (long, short), status, planned_entry, planned_stop, planned_target, thesis, entry_price, entry_at, quantity, exit_price, exit_at, fees, followed_plan (set on close), source (manual, tradingview, webull, algo; default manual), external_id (optional, unique per user and source, for idempotent imports), created_at, updated_at |
| JournalEntry | id, trade_id, phase (pre, during, post), body, created_at. Many per trade |

Rules:
- Money, prices and quantities are exact decimals (NUMERIC in Postgres, Decimal in Python). Never float. Crypto quantities are fractional.
- USD only.
- Every row is owned by a user. A user can never read or change another user's data; return 404, not 403, so ids do not leak.
- Planned stop must be on the losing side of planned entry for the trade's side (below for long, above for short). Validated on create.
- "Short" covers both direct shorts and long positions in inverse ETFs. For an inverse ETF the trade side is long and leverage_factor is negative. This distinction is documented in an ADR.

### Derived values (computed, never stored by the client)

- P/L in dollars: (exit - entry) x quantity for long, (entry - exit) x quantity for short, minus fees.
- R per share: abs(planned_entry - planned_stop). R-multiple: P/L per share / R per share, using the actual entry.
- Hold time: exit_at - entry_at.

### Analytics

`GET /analytics/summary` with optional filters (date range, strategy, symbol, side, asset_type):
- trade count, wins, losses, win rate
- average R, expectancy (in R and in dollars)
- total P/L, total fees, largest win and loss
- average hold time (winners vs losers)
- plan adherence rate (share of closed trades with followed_plan = true)
- max drawdown on the cumulative P/L curve

`GET /analytics/equity-curve`: cumulative P/L by close date.
`GET /analytics/breakdown?by=strategy|symbol|side|asset_type`: the summary metrics per group.
`GET /analytics/frequency`: trades opened per week.

### Weekly review

`GET /reviews/weekly?week=2026-W42`: trades closed and cancelled that week, the week's summary metrics, plan adherence, and every journal entry for those trades grouped by trade and phase. This is the reflection feature.

### Endpoints (v1)

- Auth: `POST /auth/register`, `POST /auth/token` (OAuth2 password flow), `GET /users/me`
- Strategies: CRUD under `/strategies`
- Trades: `POST /trades` (creates a plan), `GET /trades` (filters + pagination), `GET/PATCH/DELETE /trades/{id}`, `POST /trades/{id}/open`, `POST /trades/{id}/close`, `POST /trades/{id}/cancel`
- Journal: `POST/GET /trades/{id}/journal`, `PATCH/DELETE /journal/{entry_id}`
- Analytics and reviews as above
- Health: `GET /health` (liveness), `GET /ready` (checks the database)

### Out of scope for v1

Options, partial fills and scaling, broker CSV import, live prices, multi-currency, a frontend (OpenAPI docs at /docs are the UI), refresh tokens, email verification.

## Stack (verified October 12, 2026)

| Piece | Choice |
|---|---|
| Python | 3.15 (fall back to 3.14 only if a dependency has no 3.15 wheel; record it in an ADR) |
| Packaging | uv, with `pyproject.toml` and a committed `uv.lock` |
| Web | FastAPI (latest), Pydantic v2, pydantic-settings for config |
| Data | SQLAlchemy 2.1, Alembic, psycopg 3 |
| Database | PostgreSQL 18 in Docker (move to 19 after GA, as its own PR) |
| Auth | PyJWT, pwdlib with Argon2 |
| Tests | pytest, FastAPI TestClient on httpx2 (Starlette deprecated httpx for it; see ADR 0001), a real Postgres for integration tests |
| Quality | ruff (lint and format), mypy, pre-commit |
| Runtime | Docker multi-stage image, non-root user; docker compose for local |
| CI | GitHub Actions |

Pin exact versions in `uv.lock`. Do not add a dependency without explaining why in the PR.

## Architecture

Layered: router -> service -> repository.
- Routers: HTTP only. Parse and validate with Pydantic schemas, call a service, map domain errors to HTTP codes.
- Services: business rules (state transitions, ownership checks, P/L and R math). No FastAPI imports.
- Repositories: all SQLAlchemy queries. No business rules.
- Pydantic schemas are separate from ORM models (Create, Update, Read schemas per resource).
- Analytics math lives in pure functions with unit tests independent of the database.

## Working rules

- Every change: GitHub issue -> branch -> PR -> CI green -> AI review pass -> Michael reviews and merges. Nothing merges to `main` without Michael.
- Branch names: `<issue number>-short-name`, for example `7-trade-lifecycle`.
- Small commits, conventional commit messages.
- Start each stage in plan mode. Wait for approval before writing code.
- After each stage, explain what was built and the main Python or framework concepts used, in plain language, for someone strong in C#/.NET and new to production Python. Compare to the .NET equivalent where it helps.

## Docs the project keeps

- `docs/decisions/NNNN-title.md`: one ADR per real choice. Sections: Context, Decision, Alternatives considered (and why rejected), Consequences. Claude drafts; Michael rewrites in his own words before merge.
- `docs/learning-log.md`: dated entries. What I built, what I learned, what surprised me, bugs I hit and how I fixed them, and one interview talking point. Claude appends a stub at the end of each stage; Michael fills it in.
- `README.md`: what it is, architecture, how to run, how to test, links to the ADRs.

## Phase 1 stages

0. Scaffold: repo, uv project, tooling, `/health`, compose with Postgres, CI, CLAUDE.md, docs skeleton
1. Data layer: models, Alembic migrations, repositories, test database setup
2. Auth: register, token, current user, ownership enforcement
3. Strategies and trades CRUD plus the lifecycle transitions
4. Journal entries
5. Analytics and weekly review
6. Hardening: error format, pagination, logging, README, final Docker image

## Roadmap after Phase 1

- Phase 2: EKS, Terraform, CI/CD to ECR. Gives the API a public HTTPS URL.
- Phase 3: Integrations. TradingView alert webhook into the journal (creates a planned trade or a journal entry, shared-secret auth, idempotent). Webull OpenAPI read-only sync of filled orders to open and close trades automatically (scheduled job, later a Kubernetes CronJob). The journal never places orders.
- Phase 4: Algo trading lab, as a separate service. Rules-based versions of the owner's own setups, backtested on historical data, then paper traded in Webull's test environment. Algo trades are logged into the journal with source = algo so they can be compared against discretionary trades. No live money in scope.
- Optional: Go, as a small separate service or tool.

Each phase gets its own brief when the previous one is done. Phase 1 only needs the source and external_id fields so later phases fit without a schema rewrite.
