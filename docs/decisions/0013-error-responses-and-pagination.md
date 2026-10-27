# 0013: Error responses (RFC 9457) and pagination conventions

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

Until Stage 6, errors used FastAPI's and Starlette's defaults, which come in four shapes:

- **Domain errors** (404, 409, 422, 401): `{"detail": "message"}`.
- **Request validation:** `{"detail": [{"type", "loc", "msg", "input", "ctx", ...}]}`. Here `detail` is a list, not a string.
- **Starlette's own errors** (an unknown route, a wrong method): `{"detail": "Not Found"}`.
- **An unhandled exception:** a `text/plain` "Internal Server Error".

A client had to handle each one. And one of them leaked data: validation errors echo the rejected `input`. Posting a too-short password to `/auth/register` returned that password in the 422 body, where it could end up in client logs, proxies and error trackers.

The OpenAPI document described none of this. Routes listed their 404s and 409s with a description and no schema, and FastAPI's generated `HTTPValidationError` described a 422 shape we were about to change.

Issue #6 also asks for the pagination conventions to be settled.

## Decision

### One format: RFC 9457 problem details

**Every error response** is `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Cannot close a trade that is planned",
  "instance": "/trades/01a1…/close",
  "request_id": "03c0dc89cb9b48cfbb00eea0c08b37f7"
}
```

**The fields:**
- **`type` is `about:blank`.** RFC 9457 (section 4.2.1) says to use it when a problem has no meaning beyond its HTTP status, and that is true of every error today. `title` is then the status phrase.
- **`detail`** is the human-readable message, the same strings as before. A client that read `detail` keeps working.
- **`instance`** is the request path.
- **`request_id`** is an extension member. It matches the `X-Request-ID` response header and the log lines (ADR 0014), so a user can quote it in a bug report.

**Request validation (422)** adds `errors: [{"loc": [...], "msg": "...", "type": "..."}]`:
- **Only where, what and why.** Pydantic's `input` (the rejected value) and `ctx` (which can contain it) are deliberately dropped. The response never repeats what the client sent.
- **A domain 422** (for example, a stop on the wrong side of the entry) has no `errors` list, because it isn't about one field's shape.

**Where each error comes from:**
- **Domain errors:** `NotFoundError` → 404, `ConflictError` → 409, `InvalidInputError` → 422 and `AuthenticationError` → 401. The 401 keeps `WWW-Authenticate: Bearer` (RFC 6750).
- **`RequestValidationError`** → 422, with the sanitized `errors`.
- **Starlette's `HTTPException`:** an unknown route → 404, a wrong method → 405. The 405 keeps the `Allow` header.
- **Anything else** → 500 with the generic detail "Internal server error". The exception text never reaches the client.
  - It's caught in the request middleware (ADR 0014), so it is logged once, with the request id.

**OpenAPI documents it:**
- **`Problem` and `ValidationProblem` schemas.** Every 4xx and 5xx response references one of them, under `application/problem+json`.
- **Where each response is declared:**
  - App-level `responses` add 422 (`ValidationProblem`) and 500 to every route. Because a 422 is already declared, FastAPI no longer generates `HTTPValidationError`.
  - Each protected router declares 401.
  - The routes' own 404s and 409s go through a `problem(status, description)` helper.
- **A small post-processing step** moves the error bodies from `application/json` to `application/problem+json` in the generated document. FastAPI files additional responses under the route's own media type. The step only moves bodies that reference a `Problem` schema, so `/ready`'s 503 health body is untouched.
- **Tests:** a test walks the whole document and fails if any error response isn't a problem.

### Pagination conventions

This settles the conventions for the whole API and leaves ADR 0009's mechanism unchanged:
- **Collections that grow without bound** are paginated with keyset `Page[T]`: `{"items": [...], "next_cursor": "<id>" | null}`.
  - Query parameters: `limit` (1–200, default 50) and `cursor` (the previous page's `next_cursor`).
  - Today that's `GET /trades`.
- **Collections bounded by a parent or by the user** return a plain JSON array:
  - strategies (a handful per user)
  - a trade's journal
  - the breakdown groups
  - the frequency weeks
  - the equity curve: one point per closed trade, filterable by date
- **An invalid `cursor` or `limit` is a 422 problem.** A cursor whose trade has since been deleted still works, because keyset pagination compares ids and doesn't need the row to exist.
- **A collection that later needs pagination** switches to `Page[T]` in a new API version, rather than changing shape in place.

## Alternatives considered

- **Keep FastAPI's `{"detail": ...}`.** That's zero work, but it leaves four shapes, and the `input` leak.
- **A custom envelope** like `{"error": {"code": "...", "message": "..."}}`. That is common, but it's our invention: RFC 9457 is a standard that generic clients, API gateways and other frameworks (ASP.NET Core's `ProblemDetails`, Spring's `ProblemDetail`) already understand.
- **Specific `type` URIs per error** (such as `/problems/illegal-transition`). That's useful once clients need to branch on *which* 409 they got. Today the status code plus `detail` is enough, and RFC 9457 lets types be added later without breaking clients that ignore them.
- **Exposing exception messages on 500s,** for easier debugging. They can contain SQL, file paths or data; the request id gives the same debuggability through the logs, without the leak.
- **Paginating every list.** That's uniform, but it adds a round trip and cursor handling to collections that are small by nature. Clients that just want "my strategies" would pay for a case that can't happen.
- **Offset pagination** for the small lists. Rejected for the same reasons as in ADR 0009; it's also not needed if they aren't paginated at all.

## Consequences

- **Clients parse one error shape.** `detail` is unchanged, so existing clients keep working. Tests that compared whole error bodies now compare `detail`, or the body minus `instance` and `request_id`.
- **The OpenAPI document is truthful about errors,** and a test keeps it that way.
- **No error can echo a password or leak an exception message.**
- **Generic tooling understands the errors:** anything that recognizes `application/problem+json` (gateways, ASP.NET-style clients) can display them without custom code.
