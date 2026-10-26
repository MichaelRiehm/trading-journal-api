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
