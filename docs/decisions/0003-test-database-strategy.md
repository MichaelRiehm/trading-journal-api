# 0003: Test database strategy

- **Status:** Accepted
- **Date:** 2026-10-26
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

The brief requires a real Postgres for integration tests. Much of this schema's correctness lives in Postgres itself: CHECK constraints, composite foreign keys, `NUMERIC` precision and `timestamptz`. A fake or an in-memory database would not test any of that. Tests must stay fast and isolated, and work the same way on Windows locally and on Linux CI.

## Decision

- **Where the server comes from:** locally, compose's `db` service (`make db`); in CI, a `postgres:18` service container. Both are reached through `DATABASE_URL`.
- **A dedicated test database:**
  - Once per test session, the fixtures create a separate database: `TEST_DATABASE_URL`, or by default the database name plus `_test`.
  - They migrate it with **Alembic `upgrade head`**, so every test run also tests the migrations, and drop it at the end.
  - Dev data is never touched.
- **Isolation by rollback.** Each test runs inside an outer transaction that is rolled back afterwards. The session uses `join_transaction_mode="create_savepoint"`, so code under test can call `commit()`: it only releases a savepoint. There's no cleanup code and no ordering dependency between tests.
- **Drift and round-trip tests:**
  - A test compares the models with the migrated schema (Alembic `compare_metadata`) and fails if a model changed without a migration.
  - Another runs upgrade → downgrade → upgrade on a scratch database.
- **Fail fast.** If Postgres isn't reachable, the run stops with "start it with `make db`" instead of 28 stack traces.

## Alternatives considered

- **SQLite in memory.** Rejected: it has none of the Postgres behaviours we rely on (NUMERIC, CHECK semantics, `timestamptz`, `WITH (FORCE)`). Passing tests would prove little.
- **testcontainers-python.** Starts a throwaway Postgres container from the test run itself. Rejected for now: it's a new dependency and adds several seconds of startup per run, and compose plus a CI service already give us a server. It's worth revisiting if the setup ever needs to be zero-command.
- **Truncating tables between tests.** Slower than rolling back, and it needs an ordered list of tables to keep up to date.
- **Mocking the repositories.** Useful later for service unit tests. It doesn't test SQL, so it can't replace these tests.

## Consequences

- `make test` needs Postgres running locally (`make db`). The error message says so.
- The whole suite (28 tests, including two migration runs) takes about 3 seconds.
- Autogenerate doesn't compare CHECK constraints, so `test_constraints.py` tests each one explicitly.
