# Learning log

Dated entries, one per stage. Claude writes each entry at the end of the stage. Michael reviews them later, together with [interview-prep.md](interview-prep.md), which holds the study questions.

## 2026-10-12 — Stage 0: Scaffold

_Drafted by Claude. Not yet reviewed by Michael._

### What I built

- A uv project on Python 3.15 with a src layout.
- A FastAPI app with `GET /health` and a test.
- ruff, strict mypy and pre-commit.
- Postgres 18 and the API in Docker Compose.
- A Makefile and GitHub Actions CI.
- Branch protection on `main`.

The tooling choices are in [ADR 0001](decisions/0001-tooling.md).

### What I learned

- **Typing.** I thought mypy makes Python "strongly typed". Python is already strongly typed; what it lacks is *static* checking. mypy adds that, the way `tsc` does for JavaScript. Type hints do nothing at runtime unless a library like Pydantic or FastAPI reads them.
- **PyYAML.** I thought we'd "downgraded PyYAML to 3.14". Nothing was downgraded. PyYAML only lacked a prebuilt 3.15 wheel. It's a dependency of a dev tool (pre-commit), not of the app, so only that tool runs on 3.14.
- **uv.** The main value isn't "fewer tools". It's the lock file: the same exact packages on my laptop, in CI and in Docker.
- **src layout.** It's about testing the code as it's installed, not about third-party packages.

### What surprised me

- How much of the ecosystem lags a new Python release: PyYAML wheels, the official Docker image, and httpx being deprecated for Starlette's test client in favour of httpx2.
- Postgres 18 moved its data directory inside the Docker image, which breaks the classic volume mount.

### Bugs I hit and how I fixed them

- **CI failed at job setup.** `astral-sh/setup-uv@v10` didn't exist, because setup-uv publishes only full version tags. Fixed through #7 → #8 by pinning both actions to commit SHAs, which is also safer, since tags can be moved.
- **The Stage issues were created with off-by-one titles.** The PowerShell script that created them indexed an ordered hashtable by integer, which means by position, not by key. It went unnoticed for two weeks because only the issue numbers were checked. **Lesson:** verify what automation produced, not just that it ran.

### Interview talking point

"Before writing any code on a brand-new Python release, I checked every dependency for prebuilt 3.15 wheels on both Windows and Linux. One gap turned up, in a dev tool, so I isolated that tool on 3.14 instead of downgrading the whole project, and recorded it in an ADR with a trigger to revisit."

## 2026-10-26 — Stage 1: Data layer

_Drafted by Claude. Not yet reviewed by Michael._

### What I built

- SQLAlchemy 2.1 models for users, strategies, trades and journal entries.
- An Alembic initial migration.
- Repositories scoped by `user_id`.
- `GET /ready`.
- A compose `migrate` service that runs before the API.
- 28 tests against a real Postgres, locally and in CI.

Decisions: [ADR 0002](decisions/0002-sync-database-access.md) (sync over async), [ADR 0003](decisions/0003-test-database-strategy.md) (test database), [ADR 0004](decisions/0004-schema-conventions.md) (schema conventions).

### What I learned

- **SQLAlchemy 2.x typed models feel like EF Core entities.** `Mapped[Decimal | None]` declares both the Python type and whether the column is nullable. The `Session` is the `DbContext`: it tracks changes and writes them on `flush()` or `commit()`.
- **`flush()` vs `commit()`.** Flush sends the SQL inside the open transaction, so constraint errors surface right away. Commit makes it permanent. Repositories flush; services will commit.
- **The database can enforce business rules.** CHECK constraints and a composite foreign key make "a trade using another user's strategy" or "a closed trade without an exit price" impossible to store.
- **Rollback-per-test** gives isolated tests with no cleanup code. The savepoint trick lets code under test call `commit()` safely.

### What surprised me

- `localhost` on Windows tried IPv6 (`::1`) first. Docker only listened on IPv4, so connections stalled for the whole connect timeout, and forever without one.
- Alembic autogenerate doesn't notice CHECK constraint changes, so those need their own tests.
- Python 3.14 added `uuid.uuid7()` to the stdlib, and Postgres 18 added `uuidv7()`, the same year.

### Bugs I hit and how I fixed them

- **`alembic check` hung forever.** A stack dump (`faulthandler`) showed it stuck in psycopg's connect. The cause: `localhost` → `::1` → no answer, and Alembic's engine had no timeout. Fixed by using `127.0.0.1` in `DATABASE_URL` and adding `connect_timeout` everywhere.
- **The `migrate` container failed with "No 'script_location' key".** In the Dockerfile, `COPY alembic.ini ./` came before `WORKDIR /app`, so the files landed in `/`. Fixed by moving the `COPY` lines.
- **Three tests failed at first, and each failure was the database doing its job.** A test enum value was too long for the column; test data broke the stop-side rule; and one test read an attribute from a deleted, expired object.

### Interview talking point

"I treat the database as the last line of defence. The service validates for good error messages, but CHECK constraints and a composite foreign key make illegal trades unstorable. For example, a trade can't reference another user's strategy, even if a bug skips the service check. Every constraint has a test, because Alembic doesn't detect CHECK changes."

## 2026-10-26 — Stage 2: Auth

_Drafted by Claude. Not yet reviewed by Michael._

### What I built

- `POST /auth/register`, `POST /auth/token` (OAuth2 password flow) and `GET /users/me`.
- **Passwords:** Argon2id via pwdlib, with timing-equalized login and rehash-on-login.
- **Tokens:** HS256 JWTs with `sub`/`iat`/`exp`/`iss`/`aud`, decoded with a pinned algorithm.
- **`CurrentUser`:** a dependency that every protected route takes.
- **Domain errors** (`NotFoundError`, `ConflictError`, `AuthenticationError`), mapped to 404, 409 and 401 in one place.
- **A test that proves the 404-not-403 pattern:** another user's strategy and a missing one give identical responses.
- 67 tests, about 4 seconds.

Decisions: [ADR 0005](decisions/0005-access-tokens.md) (access tokens) and [ADR 0006](decisions/0006-password-handling.md) (password handling).

### What I learned

- **FastAPI's `Depends` is DI without a container.** A function's parameters declare what it needs, and FastAPI builds the graph per request: `get_current_user` → `AuthService` → `Session` + `Settings`. `Annotated[User, Depends(...)]` gives that a reusable name, `CurrentUser`, which acts like `[Authorize]` and `HttpContext.User` combined.
- **A JWT is signed, not encrypted.** The security comes from verifying it strictly: a pinned algorithm, required claims, issuer and audience checks, and loading the user.
- **Good auth means the error paths look identical.** Same 401 for every bad token. Same 401 and the same timing for an unknown email and a wrong password. Same 404 for "not yours" and "doesn't exist".
- **pydantic-settings composes** like ordinary classes. `Settings(DatabaseSettings)` let the migrate container run without ever seeing the signing key.

### What surprised me

- **Pydantic's validation errors echo the rejected input by default,** so a too-short `JWT_SECRET_KEY` (or a bad `DATABASE_URL` with a password in it) would be printed into the startup logs. `hide_input_in_errors=True` fixes it, and a test now checks it.
- **PyJWT warns when an HMAC key is shorter than the hash output** (64 bytes for HS512). That's how I noticed a test was relying on the wrong reason for a rejection.
- **ruff's S105 rule flags any string assigned to a name containing "token"** as a possible hardcoded password, including `token_type = "bearer"`. Those three are suppressed inline, each with a reason.

### Bugs I hit and how I fixed them

- **A commit message got a UTF-8 BOM** (`﻿chore: ...`). PowerShell 5.1's `Set-Content -Encoding utf8` writes one. Commit message files are now written with a BOM-free writer. The affected commit is on the branch only, and the squash merge replaces it.
- **The startup failure leaked the key into the logs.** Found while verifying the fail-fast behaviour, and fixed as described above.

### Interview talking point

"For another user's data the API returns 404, not 403, and that's structural, not a check someone could forget. Every repository query is scoped by the current user's id, so 'not yours' and 'doesn't exist' are the same code path. A test asserts the two responses are byte-for-byte identical. The same principle runs through login: an unknown email still pays for an Argon2 verify against a dummy hash, so response time doesn't reveal who has an account."

## 2026-10-27 — Stage 3: Strategies, trades and the lifecycle

_Drafted by Claude. Not yet reviewed by Michael._

### What I built

- **Strategies:** CRUD under `/strategies`. A duplicate name returns 409, and so does deleting a strategy that still has trades.
- **Trades:**
  - plan, list (filters plus keyset pagination), get, PATCH and delete
  - `open`, `close` and `cancel`: illegal moves return 409, and each move locks the row
- **Derived values:** pure Decimal math for P/L, R per share, R-multiple, hold time and exposure. It's computed in every response and never accepted as input.
- **Migration 0002:** leverage only on ETFs, and symbols stored uppercase.
- **Request bodies reject unknown fields.**
- 178 tests, about 13 seconds. They cover the full transition matrix and the 404-not-403 check on every endpoint that takes an id.

Decisions: [ADR 0007](decisions/0007-short-vs-inverse-etf.md) (short vs inverse ETF), [ADR 0008](decisions/0008-trade-lifecycle-and-derived-values.md) (lifecycle and derived values) and [ADR 0009](decisions/0009-keyset-pagination.md) (keyset pagination).

### What I learned

- **A state machine can be a dictionary.** `{planned: {open, cancelled}, open: {closed}}` plus one check function covers the whole lifecycle, and the test derives its 12-case matrix from the same table.
- **`exclude_unset` is what makes PATCH honest.** It separates "the client sent null" from "the client didn't send it", which C# models need extra machinery for.
- **UUIDv7 pays off again:** time-ordered ids make keyset pagination a one-line `WHERE id < :cursor`.
- **Validate the merged state before mutating the ORM object.** A rejected PATCH then leaves nothing dirty in the session, and nothing is flushed by accident later.

### What surprised me

- **Pydantic's `StringConstraints(to_upper=True)` checks its pattern *before* uppercasing,** so `"brk.b"` was rejected by an uppercase-only pattern. A `BeforeValidator` fixed it.
- **The responses changed depending on how the session was configured** (next section).

### Bugs I hit and how I fixed them

- **The create response didn't match a later read.**
  - The symptom: `"r_per_share": "5"` on create, `"5.00000000"` on GET; and `+09:00` on open, UTC on GET.
  - **Why the tests missed it:** production sessions keep objects after commit (`expire_on_commit=False`), so a response echoed the client's input. The test session expired them, so every test response was re-read from the database.
  - **The fix:** quantize decimals and convert datetimes to UTC on input, and make the test session match production.
  - Caught by the end-to-end check through compose, not by the test suite.
- **A PATCH with a typo would have been a silent no-op.** Request models now use `extra="forbid"`.
- **My own mistakes:**
  - A PowerShell read-and-rewrite of source files (`Set-Content -Encoding ascii`) turned `→` into `???`. Fixed, and I now edit files only with the editor tool.
  - A migration round trip on the dev database ran `downgrade -1` while it was at 0001, not 0002, which dropped the dev schema and whatever was in it (as far as I know, only throwaway end-to-end test data). **Lesson:** check `alembic current` first, and downgrade to an explicit revision.

### Interview talking point

"The trade lifecycle is enforced at three layers: a transition table in pure Python that turns illegal moves into 409s; `SELECT … FOR UPDATE` so two concurrent closes can't both succeed; and a CHECK constraint that makes an inconsistent row unstorable. The test suite derives every status-and-action combination from the same table, so the tests can't drift from the rules."

## 2026-10-27 — Stage 4: Journal entries

_Drafted by Claude. Not yet reviewed by Michael._

### What I built

- **Endpoints:** `POST/GET /trades/{id}/journal` and `PATCH/DELETE /journal/{entry_id}`.
- **The phase rule** ([ADR 0010](decisions/0010-journal-phase-rules.md)):
  - A phase can't run ahead of the trade; a violation returns 409. Backfilling an earlier phase is allowed.
  - The phase defaults to wherever the trade is now.
- **Ownership:** it follows the trade through a join, so another user's trade or entry returns 404.
- 225 tests, about 16 seconds. No schema change and no new dependencies.

### What I learned

- **Sometimes the right answer is *no* lock, and you can prove it.** Statuses only move forward, and each status allows a superset of the previous one's phases. So a check that passed can't be invalidated by a concurrent transition. That's a one-line property test over the lifecycle table, and it fails if a future change breaks the reasoning.
- **Rules as data, again.** Like the lifecycle in Stage 3, the phase rule is a dictionary. The tests derive their matrix from it, and a unit test checks it against the lifecycle table.
- **Nested routes for creating, flat routes for editing.** `/trades/{id}/journal` says which trade an entry belongs to. `/journal/{entry_id}` lets a client edit without knowing the trade.

### What surprised me

- **`updated_at` can't visibly change inside a test.** Postgres's `now()` is the *transaction's* start time, and each test runs in one rolled-back transaction. So "updated_at advances" is only provable against the real stack, where I checked it through compose. Inside the suite, the test asserts `updated_at >= created_at` and that the edit persisted.

### Bugs I hit and how I fixed them

- **None in the code this stage.** One near miss in my own process: I added a lint suppression to a line that didn't need it, and removed it on review.

### Interview talking point

"Trade transitions take a row lock, but journal writes deliberately don't, and I can show why. The allowed journal phases only grow as a trade moves through its lifecycle, so any entry that passed the check stays valid whatever transition commits next. That invariant is a unit test over the same lifecycle table the code uses. If someone changes the rules in a way that breaks it, the test tells them the locking question is back."
