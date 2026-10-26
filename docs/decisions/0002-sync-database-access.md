# 0002: Synchronous database access

- **Status:** Accepted
- **Date:** 2026-10-26
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

FastAPI supports both `async def` and plain `def` endpoints. SQLAlchemy 2.1 offers a synchronous `Session` and an `AsyncSession`, and psycopg 3 supports both modes. The choice affects every layer: endpoints, services, repositories and tests.

The workload is one user, or a handful, journaling trades. There's no fan-out to slow external services in Phase 1.

## Decision

- Use **synchronous SQLAlchemy** (`Session`, psycopg 3) with **plain `def` endpoints** wherever the database is involved.
- FastAPI runs `def` endpoints on a thread pool, so a blocking query never stalls the event loop.
- `/health` stays `async def`, because it does no I/O.

## Alternatives considered

- **`AsyncSession` with `async def` endpoints.** Async pays off when a process spends most of its time waiting on many concurrent slow I/O calls, such as fan-out to external APIs or websockets. That doesn't describe this API. It also brings real costs:
  - lazy-loaded relationships raise errors under async unless every load is explicit
  - it needs the `greenlet` dependency
  - async-specific fixtures in tests
  - an easy trap: calling blocking code inside `async def` stalls every request

  The 3.15 wheels exist (`greenlet` has cp315 wheels), so this is a choice, not a constraint.
- **Mixed: async endpoints that call sync code.** That's the worst of both: blocking calls on the event loop.

## Consequences

- Simpler code and tests. A stack trace reads top to bottom.
- Concurrency is bounded by the thread pool (40 threads by default) and the connection pool. That's ample for this workload. If it ever isn't, the first lever is more workers (processes), not async.
- Phase 3 integrations (TradingView webhooks, Webull sync) can still use async HTTP clients in their own code paths if that helps.
- Rule of thumb for the codebase: **`def` when the endpoint touches the database; `async def` only when everything inside is non-blocking.**
