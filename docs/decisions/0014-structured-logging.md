# 0014: Structured logging and request ids

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

The app had no logging of its own. Uvicorn printed text access lines (`"GET /trades HTTP/1.1" 200`), with no way to link a line to an error response, no user, and no timing. An unhandled exception was logged by uvicorn as a text traceback.

Issue #6 requires structured logs that "contain no secrets or password hashes". Three places could leak one:

- **Request data:** headers carry the bearer token, and bodies carry passwords.
- **Query strings:** they have no secrets today, but nothing stops one being added.
- **Database errors:** SQLAlchemy includes the bound parameters in exception messages by default. A failed `INSERT INTO users` would print the email and the password hash into any log of that error.

## Decision

### JSON lines with the standard library

- **No new dependency.** We use stdlib `logging` with one small `JsonFormatter` (`logging_config.py`). structlog would be the next step if logging grew (processors, bound loggers); one formatter class doesn't justify a dependency.
- **One JSON object per line, on stdout.** That suits Docker, and any log collector can parse it.
- **The fields:**
  - always: `timestamp` (UTC, milliseconds), `level`, `logger`, `message`
  - during a request: `request_id`
  - once authenticated: `user_id`
  - after an exception: `exception`, the formatted traceback
- **Extra fields come from an allowlist:** `method`, `path`, `status`, `duration_ms`. Anything else passed with `extra=` is dropped, so a careless `logger.info("...", extra={"password": ...})` still doesn't leak.
- **`configure_logging()` routes everything, uvicorn's loggers included,** through the one JSON handler. It runs when the app is created, so uvicorn's own startup lines come out as JSON too.
- **Uvicorn's access log is turned off** (`--no-access-log`, and its logger silenced), because the app writes a better one.
- **The level comes from `LOG_LEVEL`** (default `INFO`). It is read by a separate `LoggingSettings`, so configuring logging needs no JWT key or database URL.

### A request middleware

`RequestContextMiddleware` is a plain ASGI middleware. It does four things:

1. **Assigns a request id.** It accepts a client's `X-Request-ID` only if it is 1–64 characters of `[A-Za-z0-9._-]`, so it can't inject newlines or fake JSON into logs or headers. Otherwise it generates one (a UUID4 in hex). The id is returned in the `X-Request-ID` response header and in every problem body (ADR 0013).
2. **Writes one access line per request:** `method`, `path` (never the query string), `status`, `duration_ms`, and `user_id` if the request authenticated.
3. **Catches unhandled exceptions.** It logs each one once, with its traceback and request id, and returns the generic 500 problem. If the response had already started, it re-raises instead, because a second response can't be sent.
4. **Holds the per-request context** in a `ContextVar` pointing to a small mutable `RequestContext` (`request_id`, `user_id`).
   - `get_current_user` sets `user_id` on it.
   - Why mutable: FastAPI runs sync dependencies in a worker thread with a *copy* of the context. Setting a ContextVar there would be invisible to the middleware afterwards, but changing the shared object is not.

### Secrets stay out by construction

- **What is never logged:** headers, bodies, query strings, and database exception messages with their parameters.
- **The engine is created with `hide_parameters=True`,** so SQLAlchemy errors say `[SQL parameters hidden due to hide_parameters=True]` instead of quoting the values.
- **A test registers, logs in, fails a login and hits a 409,** then asserts that the password, the wrong password, the stored hash and the token appear nowhere in the captured log output.

## Alternatives considered

- **structlog or python-json-logger.** Either is good. But the formatter is about 30 lines, and the brief asks for a reason before any new dependency.
- **Starlette's `BaseHTTPMiddleware` (`@app.middleware("http")`).** It's simpler to write, but it wraps the response in extra layers and has a history of edge cases with streaming and exceptions. A plain ASGI middleware is about 50 lines and does exactly what's needed.
- **Keep uvicorn's access log.** It's text, it has no request id or user, and logging every request twice is noise.
- **Log the full request URL.** A query string is a classic place for tokens and personal data to end up; the path is enough to debug with.
- **Trust any client-sent request id.** It would let a client write arbitrary text into our logs (log injection), so only a safe shape is accepted.
- **Text logs locally, JSON in production.** That's a nicer read in a terminal, but it's two code paths and two sets of tests. `docker compose logs api | jq` reads JSON fine.

## Consequences

- **Every response and log line can be correlated** through `X-Request-ID`, including the 500 a user reports.
- **Log processors can filter** by `user_id`, `path` or `status` without regex parsing.
- **Developers running uvicorn on the host** also get JSON lines; `uv run uvicorn … | jq` is the way to read them.
- **Phase 2** (Kubernetes, a log collector) can consume these logs as they are. Tracing (OpenTelemetry) can reuse the request-context middleware.
