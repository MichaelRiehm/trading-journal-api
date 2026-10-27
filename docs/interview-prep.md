# Interview prep

What to be able to explain about this project, collected stage by stage while it's being built. Claude keeps this current. Michael reviews it later.

**How to use it:** For each item, read the question, answer it out loud without looking, then compare with the short answer. Tick the box once you can explain it in your own words and handle one follow-up question. The linked ADR or file has the full reasoning.

## The project in 60 seconds (draft, refined each stage)

> A REST API for swing traders. You plan a trade (entry, stop, target, thesis) before entering, record the actual entry and exit, journal before, during and after, and get analytics: win rate, R-multiples, expectancy, drawdown, plan adherence, and a weekly review. It's Python 3.15 with FastAPI, SQLAlchemy and PostgreSQL 18, in a layered router → service → repository design, with strict typing, CI and branch protection. Next, it gets deployed to AWS EKS with Terraform.

---

## Stage 0: Tooling and repo setup

### Packaging and environments

- [ ] **What does uv do, and why use it?**
  It replaces pyenv, venv, pip and pip-tools. The real win is the lock file:
  - `pyproject.toml` declares version ranges.
  - `uv.lock` pins every package, including transitive ones, with hashes.
  - Laptop, CI and Docker all install the same thing, and `uv sync --locked` fails if the lock is stale. It's the .NET equivalent of `packages.lock.json` in locked mode.

  → [ADR 0001](decisions/0001-tooling.md)
- [ ] **Why does Python need a virtual environment (`.venv`) when .NET doesn't?**
  - Python has one flat `site-packages` per interpreter, so two projects can't use different versions of a package side by side.
  - .NET resolves package versions per project from a global cache.
  - A venv gives each project its own `site-packages`. uv keeps a global cache and links files from it into `.venv`.
- [ ] **What is a wheel, and what does `cp315` mean?**
  - A wheel is a prebuilt package.
  - Pure-Python packages ship one wheel for every version (`py3-none-any`).
  - Packages with C or Rust inside need a wheel per Python version (`cp315` = CPython 3.15). Without one, the installer has to compile from source.
  - That's why brand-new Python releases lag. We checked with `uv pip compile --only-binary :all: --python-version 3.15`.
- [ ] **PyYAML had no 3.15 wheel. Did you downgrade?**
  No, and this is the common misconception to avoid. PyYAML isn't our dependency; pre-commit, a dev tool, needs it.
  - We installed pre-commit separately on 3.14 (`uv tool install`, like `dotnet tool install -g`).
  - The app stays fully on 3.15, and the checks pre-commit runs still use the project's 3.15 environment.
  - The brief allowed moving everything to 3.14. We didn't need to.

  → [ADR 0001](decisions/0001-tooling.md)
- [ ] **What is the src layout and why use it?**
  - The code lives in `src/trading_journal/`, so Python can't import it just because it's in the current folder; it has to be installed.
  - Tests therefore import the package the way production does, and packaging mistakes fail the tests instead of the deployment.
- [ ] **What's the difference between a dependency group and a regular dependency?**
  - `[dependency-groups] dev` (pytest, ruff, mypy, httpx2) is installed for development and CI.
  - Docker installs with `--no-dev`, which is like test-only package references never shipping.

### Code quality

- [ ] **Python is "strongly typed". So why mypy?**
  - Python is strongly typed (`"1" + 1` raises an error) but *dynamically* typed: types are only checked at runtime, and type hints are ignored at runtime.
  - mypy adds *static* checking before the code runs, like `tsc` for TypeScript.
  - C# differs because the compiler and the runtime both enforce types.
  - In this project, Pydantic validates data at runtime, and mypy checks the code statically.
- [ ] **What's the difference between ruff's linter and its formatter?**
  - The linter finds likely bugs and security problems: unused imports, mutable default arguments, bandit `S` rules.
  - The formatter rewrites layout, like `dotnet format` or Prettier.
  - One tool replaces black, isort and flake8.
- [ ] **Why do pre-commit hooks run `uv run ruff` instead of the official ruff hook?**
  So the hooks use the exact versions in `uv.lock`. A separately pinned hook version could drift from CI.

### FastAPI basics

- [ ] **How does a FastAPI route work, compared with ASP.NET Core?**
  - It's closest to Minimal APIs.
  - `@router.get("/health")` is a decorator: a function that runs at import time and registers the handler. A C# attribute, by contrast, is passive metadata read through reflection.
  - `APIRouter` groups routes like `MapGroup` or a controller, and `include_router` registers the group.

  → [api/health.py](../src/trading_journal/api/health.py), [main.py](../src/trading_journal/main.py)
- [ ] **How does FastAPI know the response shape?**
  It reads the return type annotation (`-> HealthResponse`) at runtime, then validates, serializes and documents the output in OpenAPI. In .NET that takes `ActionResult<T>`, `[ProducesResponseType]` and Swashbuckle together.
- [ ] **uvicorn, ASGI, Kestrel?**
  uvicorn is the server (Kestrel's role). ASGI is the contract between the server and the app. The FastAPI `app` object is an ASGI app.
- [ ] **`async def` vs `def` endpoints?**
  - `async def` runs on the event loop, so anything blocking inside it stalls every request.
  - Plain `def` runs in a thread pool automatically.
  - Choose based on whether the code inside is truly non-blocking. → Stage 1 database access decision.
- [ ] **How do the tests reach the app?**
  - `TestClient(create_app())` runs the app in memory with no network, like `WebApplicationFactory<Program>`.
  - pytest fixtures are injected by parameter name, like xUnit constructor injection, and the code after `yield` is the teardown.

### Containers

- [ ] **Walk through the Dockerfile.**
  - Multi-stage: the builder installs Python and the locked dependencies, and the runtime stage copies in only the interpreter and the venv.
  - It runs as a non-root user.
  - Dependencies come before source code, so the dependency layer stays cached.
  - `.dockerignore` keeps the Windows `.venv` and `.env` out of the image.

  → [Dockerfile](../Dockerfile)
- [ ] **Why not `FROM python:3.15-slim`?**
  It didn't exist when we started, only release candidates. We installed the same CPython 3.15.0 build through uv on `debian:trixie-slim`. The official image was published on 2026-10-24, and the switch is planned for Stage 6.
- [ ] **What changed in the Postgres 18 Docker image?**
  The data moved to `/var/lib/postgresql/18/docker`, so the volume mounts at `/var/lib/postgresql`. The old `/var/lib/postgresql/data` mount fails on 18.

  → [compose.yaml](../compose.yaml)

### CI and repo security

- [ ] **Why are GitHub Actions pinned to commit SHAs?**
  - Git tags can be moved. Whoever controls an action's repo can repoint a tag at new code, and every workflow using that tag runs it with that workflow's secrets.
  - That's what happened in the March 2025 `tj-actions/changed-files` compromise.
  - A SHA is a hash of the commit's contents and can't be repointed. The trade-off is that pins don't update themselves; Dependabot can bump them.

  → [ci.yml](../.github/workflows/ci.yml)
- [ ] **What does branch protection on `main` enforce?**
  - Every change goes through a PR.
  - The `ci` check must pass, and only a result from the GitHub Actions app counts.
  - The branch must be up to date with `main`.
  - Admins are included, and force pushes and deletion are blocked.
  - 0 approvals are required, because GitHub doesn't let you approve your own PR.
- [ ] **How did you decide to trust a new dependency (httpx2)?**
  - Starlette's own source prefers it.
  - It's maintained by httpx's original author under the pydantic org.
  - The release on GitHub matches the one on PyPI.
  - Caveat: there's no PyPI provenance attestation yet.

  → [ADR 0001](decisions/0001-tooling.md)

### Process

- [ ] **What's an ADR, and why keep ADRs in the repo?**
  - A short record of a real decision: Context, Decision, Alternatives considered, Consequences.
  - Kept in git, it's versioned and reviewed with the code it explains.
  - It's append-only: a reversed decision gets a new ADR that supersedes the old one.

### Bug stories ("tell me about a bug you hit")

- [ ] **The first CI run failed before any code ran.** The workflow used `astral-sh/setup-uv@v10`, but setup-uv only publishes full tags like `v10.3.0`. Fixed through issue #7 → PR #8 by pinning to SHAs, which turned a typo-class bug into a security improvement. **Lesson:** verify that a ref exists, not just that a release exists.

---

## Stage 1: Data layer

### SQLAlchemy and Alembic (vs EF Core)

- [ ] **How does SQLAlchemy map to EF Core?**

  | SQLAlchemy | EF Core |
  |---|---|
  | `Session` | `DbContext`, with change tracking |
  | `select(Trade).where(...)` | LINQ |
  | `Mapped[...]` classes | entities |
  | Alembic | EF migrations |
  | `alembic revision --autogenerate` | `dotnet ef migrations add` |
  | `alembic upgrade head` | `dotnet ef database update` |

  → [models/](../src/trading_journal/models/)
- [ ] **What's the difference between `flush()` and `commit()`?**
  - Flush sends pending SQL inside the current transaction: you get generated values and constraint errors now, but nothing is permanent.
  - Commit ends the transaction.
  - Our repositories flush, and services decide when to commit (unit of work).
- [ ] **What does `Mapped[Decimal | None]` mean?**
  The Python type (checked by mypy) and the nullability (`None` → `NULL` allowed). The column type comes from the type map (`Decimal` → `NUMERIC(20,8)`), so most columns need no extra arguments.
- [ ] **Why autogenerate a migration and then review it?**
  Autogenerate diffs the models against the database, which is a big time-saver, but it misses things like CHECK constraint changes and renames (it sees a rename as a drop plus an add). Always read the generated file.
- [ ] **How do you know the models and migrations match?**
  A test runs Alembic's `compare_metadata` against the freshly migrated test database. A non-empty diff means someone changed a model without a migration. Another test runs upgrade → downgrade → upgrade.

  → [test_migrations.py](../tests/test_migrations.py)
- [ ] **How do migrations run in deployment?**
  As a separate one-shot step before the app starts. In compose, the `migrate` service runs, and `api` waits for it with `service_completed_successfully`. In Kubernetes, that becomes a Job or an init container. Why not run migrations on app startup? Several replicas would race, and a failed migration should block the deploy, not crash-loop the app.

### Schema design

- [ ] **Why UUIDv7 instead of auto-increment ids?**
  - Sequential ids leak counts ("I'm trade #12") and invite enumeration (try /trades/13).
  - Random UUIDv4s fix that but scatter inserts across the index.
  - v7 is time-ordered and unguessable.
  - `uuid.uuid7()` is in the stdlib since Python 3.14.

  → [ADR 0004](decisions/0004-schema-conventions.md)
- [ ] **Why `NUMERIC(20, 8)` and `Decimal`, never float?**
  Floats are binary fractions: `0.1 + 0.2 != 0.3`. Money must be exact. 20/8 gives 12 integer digits and 8 decimals, enough for sub-cent crypto prices and fractional quantities.
- [ ] **Why VARCHAR plus CHECK instead of native Postgres ENUMs?**
  Adding a native enum value needs `ALTER TYPE` (with transaction caveats), and removing one is painful. With VARCHAR plus CHECK, a change is an ordinary migration. `source` will grow in later phases.
- [ ] **Why put business rules in the database if the service validates anyway?**
  Defence in depth. The service gives good error messages, and the database guarantees correctness against bugs, scripts and manual fixes. For example, `ck_trades_status_fields` makes "a closed trade without an exit price" impossible to store.
- [ ] **What is the composite foreign key on trades for?**
  `(strategy_id, user_id) → strategies(id, user_id)`. A trade's strategy must belong to the *same user*, enforced by Postgres, not just by code. It needs a unique constraint on `strategies(id, user_id)` as its target.
- [ ] **How is ownership enforced in the repositories?**
  Every lookup takes `user_id` (`get(user_id, trade_id)`). Another user's row simply isn't found, and the service returns 404. There's no "load it, then check the owner" step to forget.
- [ ] **Why a constraint naming convention?**
  Deterministic names (`ck_trades_stop_on_losing_side`) make migrations reproducible and error messages readable. Without one, Postgres invents names that differ between databases.

### Sync vs async, and testing

- [ ] **Why synchronous SQLAlchemy in an async framework?**
  - FastAPI runs plain `def` endpoints on a thread pool, so blocking DB calls never stall the event loop.
  - Async pays off with many concurrent slow I/O waits, which isn't this workload, and adds pitfalls (lazy loading errors, blocking-in-async bugs).
  - Rule: `def` for DB endpoints, and `async def` only if everything inside is non-blocking.

  → [ADR 0002](decisions/0002-sync-database-access.md)
- [ ] **How do your integration tests stay isolated and fast?**
  - One test database per session, created and migrated by Alembic.
  - Each test runs in a transaction that is rolled back.
  - `join_transaction_mode="create_savepoint"` lets code under test call `commit()` safely.
  - 28 tests take about 3 seconds.

  → [ADR 0003](decisions/0003-test-database-strategy.md), [conftest.py](../tests/conftest.py)
- [ ] **Why not SQLite for tests?**
  It lacks the Postgres behaviour we depend on (NUMERIC, CHECK semantics, `timestamptz`). Tests would pass against a different database than production.
- [ ] **What's the difference between liveness (`/health`) and readiness (`/ready`)?**
  - Liveness says the process is alive; if it fails, restart the process.
  - Readiness says the app can serve traffic, here meaning the database is reachable; if it fails, stop sending traffic, but don't restart.
  - These map directly onto Kubernetes probes in Phase 2.

### Bug stories

- [ ] **`alembic check` hung forever.** A stack dump with `faulthandler.dump_traceback_later` showed it stuck in psycopg's connect.
  - `localhost` resolved to IPv6 `::1` first, and Docker Desktop only publishes on `127.0.0.1`, so the connection got no answer instead of a fast refusal.
  - Fixed with `127.0.0.1` and a `connect_timeout` everywhere.
  - **Lessons:** always set network timeouts, and dump a stack when something hangs rather than guessing.
- [ ] **The migrate container said "No 'script_location' key".** `COPY` before `WORKDIR` in the Dockerfile put `alembic.ini` in `/`. **Lesson:** in a Dockerfile, relative paths follow the `WORKDIR` in effect at that line.

---

## Stage 2: Auth

### Tokens

- [ ] **What's inside a JWT, and is it encrypted?**
  - It's three base64url parts: `header.payload.signature`.
  - It's **signed, not encrypted.** Anyone can read the claims (try pasting one into jwt.io), but nobody can change them without the key.
  - So: never put secrets in a JWT. Ours carries `sub`, `iat`, `exp`, `iss` and `aud`.

  → [ADR 0005](decisions/0005-access-tokens.md)
- [ ] **HS256 vs RS256: when would you use each?**
  - **HS256:** one shared secret both signs and verifies. Right when the issuer and verifier are the same service, as here.
  - **RS256 or EdDSA:** a private key signs, and a public key verifies. Right when *other* services must verify tokens without being able to mint them; they fetch the public key from a JWKS endpoint.
  - The ASP.NET equivalent is `SymmetricSecurityKey` vs `RsaSecurityKey` in `TokenValidationParameters`.
- [ ] **What is the `alg: none` attack, and how does your code prevent it?**
  - An attacker sends a token with header `alg: none` and no signature. A naive library trusts the header and skips verification.
  - In the related algorithm-confusion attack, the attacker switches RS256 to HS256 and signs with the *public* key as an HMAC secret.
  - Defence: decode with a pinned `algorithms=["HS256"]` list, never the token's own header. There's a test for each case.
- [ ] **Stateless JWTs can't be revoked. How do you live with that?**
  - Short expiry (60 minutes), no refresh tokens, and the user is loaded on every request, so a deleted user is locked out at once.
  - If revocation is ever needed: a per-user "valid after" timestamp compared with `iat`, or a deny-list of `jti` values. Either brings back a lookup, which is the price of revocation.
- [ ] **JWT vs server-side sessions?**
  - **Sessions:** instant revocation, but a shared store (Redis or the database) and CSRF handling if cookies are used.
  - **JWTs:** no shared state, so any replica can verify. That suits Kubernetes.
  - For one service with one user, both work. I chose JWTs because the brief and the OAuth2 flow in `/docs` expect bearer tokens.
- [ ] **Why does every 401 look the same?**
  Missing, expired, tampered and deleted-user tokens all return the same status, message and `WWW-Authenticate: Bearer` header. Details would help an attacker and not a legitimate client. RFC 6750 requires the header.
- [ ] **What's the OAuth2 "password flow", and isn't it deprecated?**
  - The client posts `username` and `password` as a form to the token endpoint and gets back an access token.
  - OAuth 2.1 drops it, because it hands the password to a client app. That matters for *third-party* clients.
  - For a first-party API it's just a login form. We use its shape because FastAPI's `/docs` "Authorize" button speaks it.

### Passwords

- [ ] **Why Argon2id over bcrypt?**
  - Argon2id is *memory-hard*: each guess needs megabytes of RAM, which makes GPU and ASIC cracking far more expensive.
  - bcrypt is CPU-hard only, and it silently truncates passwords at 72 bytes.
  - OWASP's first choice is Argon2id.

  → [ADR 0006](decisions/0006-password-handling.md)
- [ ] **What's a salt, and where is it stored?**
  - It's random bytes mixed into each hash, so identical passwords produce different hashes and precomputed (rainbow) tables are useless.
  - It's stored inside the PHC hash string itself (`$argon2id$v=19$m=…$salt$hash`), together with the parameters. That's why there's no salt column.
- [ ] **What's a timing attack on login, and how did you prevent it?**
  - If "unknown email" returns faster than "wrong password", response times reveal which emails are registered.
  - Defence: for an unknown email, verify against a dummy hash anyway, so both paths pay the Argon2 cost and return the same 401.
- [ ] **What happens when you want stronger hashing parameters later?**
  `verify_and_update` notices that a stored hash uses old parameters and, on successful login, returns a fresh hash, which we save. Upgrades roll out as users log in, with no migration. There's a test that plants a weak hash and checks it gets upgraded.
- [ ] **Why 12–128 characters and no "must contain a symbol" rules?**
  - NIST 800-63B: length beats composition rules, which mostly produce `Password1!`.
  - The upper cap stops someone from submitting huge inputs to burn CPU.

### FastAPI and design

- [ ] **How does `Depends` compare with ASP.NET Core DI and `[Authorize]`?**
  - `Depends(fn)` declares "call `fn` and inject its result", resolved per request. Dependencies can depend on other dependencies.
  - `CurrentUser = Annotated[User, Depends(get_current_user)]` plays the role of `[Authorize]` plus `HttpContext.User` in one parameter: if the dependency raises, the endpoint never runs.
  - The key difference: there's no container registration. The function *is* the registration.
  - Tests swap dependencies with `app.dependency_overrides`, like replacing a service in `WebApplicationFactory`.
- [ ] **401 vs 403 vs 404: which do you return for another user's trade, and why?**
  - **401:** we don't know who you are.
  - **403:** we know who you are, and you can't do this.
  - For another user's resource we return **404**. A 403 would confirm that the id exists.
  - Queries are scoped by `user_id`, so "not yours" and "doesn't exist" are literally the same code path. A test asserts the two responses are identical.
- [ ] **How do services report errors without knowing about HTTP?**
  - Services raise domain errors (`NotFoundError`, `ConflictError`, `AuthenticationError`).
  - One exception-handler table in `api/errors.py` maps them to 404, 409 and 401.
  - That's the same idea as ASP.NET exception-handling middleware or `ProblemDetails` mapping.
- [ ] **Why split `Settings` into `DatabaseSettings` and `Settings`?**
  Least privilege. The migrate job needs only the database URL, so it never receives the JWT signing key. The settings also fail fast: the app refuses to start with a missing or short key, and the validation error never echoes the rejected value (`hide_input_in_errors`).
- [ ] **Argon2 is slow on purpose. Doesn't that block FastAPI?**
  Not with plain `def` endpoints: FastAPI runs them on a thread pool, and argon2-cffi releases the GIL while hashing. Inside an `async def` endpoint, the same call would block the event loop for every request.

---

## Stage 3: Strategies, trades and the lifecycle

### The domain (be ready to explain it to a non-trader)

- [ ] **What is an R-multiple, and why do traders use it?**
  - R is the risk you planned per share: the distance from entry to stop.
  - The R-multiple is the result in units of that risk. +2R means you made twice what you risked, and −1R means you hit your stop.
  - It makes trades of different sizes and prices comparable, and **expectancy** (the average R) says whether a strategy makes money in the long run.
  - Ours is **net of fees** and uses the **actual** entry: the honest version.

  → [ADR 0008](decisions/0008-trade-lifecycle-and-derived-values.md)
- [ ] **Why is buying an inverse ETF a "long" trade?**
  - `side` is the position you hold. You *bought* SQQQ, and you profit if its price rises.
  - Calling it a short would flip the P/L sign. The bet on a falling market is captured separately by the computed `exposure` field (bearish).
  - Leverage never enters the P/L math, because it's already in the ETF's price.

  → [ADR 0007](decisions/0007-short-vs-inverse-etf.md)

### State and concurrency

- [ ] **How is the trade lifecycle enforced?**
  - Three layers:
    1. A pure transition table in `domain/lifecycle.py`; illegal moves raise `ConflictError` → 409.
    2. A row lock for each transition.
    3. A CHECK constraint that makes inconsistent rows unstorable.
  - A test derives the full 4×3 status/action matrix from the table, so the test and the code can't drift.
- [ ] **Why 409 for an illegal transition, and not 400 or 422?**
  - **409 Conflict** means the request is valid, but it conflicts with the resource's *current state*. Closing an open trade is fine; closing a planned one isn't.
  - **422** is for a request that's wrong in itself (stop on the wrong side, a malformed price), whatever the state.
- [ ] **Two "close" requests arrive at the same time. What happens?**
  - Each loads the trade with `SELECT … FOR UPDATE`. The second blocks until the first commits, then sees `closed` and gets a 409.
  - Without the lock, both could read `open` and both "succeed", with the last write winning.
- [ ] **Pessimistic vs optimistic locking: when would you use each?**
  - **Pessimistic** (`FOR UPDATE`): lock while you work. Simple and correct for short transactions with real contention.
  - **Optimistic** (a version column, `UPDATE … WHERE version = :v`, then check rows affected): no locks, and conflicts are detected at write time. It's better for long user edit sessions where conflicts are rare.
  - EF Core does optimistic with `[ConcurrencyCheck]` or a `rowversion` column and throws `DbUpdateConcurrencyException`.
- [ ] **Why can't the plan be edited after the trade is opened?**
  The plan is the record that `followed_plan` and plan adherence are measured against. Editing it after entry would rewrite history to look disciplined. `strategy_id` can still change, because that's classification, not history.

### API design

- [ ] **Keyset vs offset pagination?**
  - **Offset** (`OFFSET 100 LIMIT 50`) shifts when rows are inserted between pages, so you get duplicates or gaps. It also gets slower deeper in, because skipped rows are still read.
  - **Keyset** (`WHERE id < :last_seen ORDER BY id DESC LIMIT 50`) is stable and uses an index for every page. The cost is no "jump to page N".
  - UUIDv7 makes the id itself a time-ordered key, so the cursor is just the last id.

  → [ADR 0009](decisions/0009-keyset-pagination.md)
- [ ] **How does your PATCH tell "set this to null" apart from "don't change it"?**
  - `model_dump(exclude_unset=True)` returns only the fields the client actually sent. So `{"strategy_id": null}` clears it, and `{}` leaves it alone.
  - A model validator rejects `null` for required fields.
  - In ASP.NET you'd need `JsonPatchDocument` or a custom "optional" wrapper to get the same distinction.
- [ ] **Why reject unknown fields in request bodies?**
  With the default (ignore), a typo in a PATCH (`planed_stop`) returns 200 and silently changes nothing. Sending a derived value like `pnl` would also look accepted. `extra="forbid"` turns both into a 422.
- [ ] **Why are money values JSON strings?**
  Most JSON parsers, JavaScript's included, read numbers as binary floats, so `0.1 + 0.2` problems come back on the client. A string keeps the exact decimal, and the client parses it with a decimal type.
- [ ] **Where do business rules live vs validation rules?**
  - **Shape** (types, ranges, symbol format, 8 decimal places) lives in Pydantic schemas: the API's contract, documented in OpenAPI.
  - **Business rules** (stop side, leverage only on ETFs, transitions, ownership of the strategy) live in services, so create and PATCH share them.
  - **Integrity** lives in database constraints, as the backstop.

### Python and Pydantic

- [ ] **What's `Decimal` rounding, and why `ROUND_HALF_EVEN`?**
  - `quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)` rounds to 8 places. Halfway cases go to the even digit, so rounding errors don't add up in one direction over many trades. It's called banker's rounding.
  - C#'s `Math.Round(decimal)` defaults to the same `MidpointRounding.ToEven`.
- [ ] **What's a `computed_field`?**
  - A `@property` on a Pydantic model that's included in the serialized output and the OpenAPI schema. It's like a C# get-only property that `System.Text.Json` serializes.
  - We use it so P/L, R and exposure appear in every trade response, but can never be set.
- [ ] **What's `class Page[T](BaseModel)`?**
  PEP 695 generic syntax (Python 3.12+): a generic Pydantic model, like `Page<T>` in C#. `Page[TradeRead]` gets its own concrete OpenAPI schema.
- [ ] **What's the difference between a `BeforeValidator` and an `AfterValidator`?**
  - **Before** runs on the raw input, before type and constraint checks. We use one to uppercase symbols before the pattern check.
  - **After** runs on the validated value. We use one to quantize decimals and convert datetimes to UTC.
  - The gotcha: `StringConstraints(to_upper=True)` runs its pattern check *first*, which rejected `"brk.b"`.

### Bug stories

- [ ] **A create response said `"100"`, but a later read said `"100.00000000"`.**
  - The production session doesn't expire objects on commit, so the response was built from the client's input. The test session *did* expire them, so tests always re-read from the database and never saw it.
  - The fix had two parts: normalize inputs to the stored form, and make the test session match production.
  - **Lesson:** test fixtures that differ from production config hide bugs.

---

## Stage 4: Journal entries

- [ ] **Should a journal entry's phase match the trade's status?**
  - Not exactly. **A phase can't run ahead of the trade** (no `post` before close, no `during` on a trade that never opened), but earlier phases can be backfilled.
  - A strict match would block the real "log it afterwards" workflow; no rule would let nonsense into the weekly review.
  - A violation returns 409, and the phase defaults to the trade's current stage.

  → [ADR 0010](decisions/0010-journal-phase-rules.md)
- [ ] **Trade transitions lock the row. Why don't journal writes?**
  - The lock exists to stop a check from being invalidated by a concurrent change. Here that can't happen: statuses only move forward, and each status allows a superset of the previous one's phases.
  - A valid entry stays valid whatever transition commits next. A unit test asserts that property, so a future rule change that breaks it fails the build.
  - The general skill: **reason from invariants about when you *don't* need a lock**, instead of adding locks everywhere.
- [ ] **How is ownership enforced for a row with no `user_id` column?**
  - Through its parent. `SELECT … FROM journal_entries JOIN trades ON … WHERE entry.id = :id AND trades.user_id = :me`.
  - Another user's entry simply isn't found, giving a 404 identical to a missing one. A parametrized test covers all four journal endpoints.
  - Storing `user_id` on entries would duplicate data that could disagree with the trade.
- [ ] **Nested or flat URLs: `/trades/{id}/journal` or `/journal/{id}`?**
  - Both, for different jobs. **Nested for collection operations** (create and list), where the parent is the context.
  - **Flat for the item** (PATCH and DELETE): the entry id is enough, and the client doesn't need to know the trade.
  - That's a common REST convention. GitHub's REST API does the same with issue comments: `POST /repos/{owner}/{repo}/issues/{number}/comments` to create, `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` to edit.
- [ ] **Why can journal entries be edited after the fact when the trade plan can't?**
  - The plan is structured data that analytics (plan adherence) measures against, so editing it would falsify numbers.
  - The journal is free text no number depends on. Transparency (`updated_at` in every response) is enough, and Stage 5 can flag edited entries.
- [ ] **Why can't a test see `updated_at` change?**
  Postgres's `now()` returns the **transaction start time**, constant for the whole transaction, and each test is one rolled-back transaction. Production requests are separate transactions, so it does advance, which I verified against the running stack. `clock_timestamp()` gives wall-clock time within a transaction, if that's ever needed.

---

## Stage 5: Analytics and weekly review

- [ ] **How does a breakeven trade count?**
  - **Exactly 0 net P/L after fees** is breakeven: neither a win nor a loss, reported separately. A gain smaller than the fees is a loss.
  - **It stays in the denominator** of the win rate and plan adherence.
  - **Why exactly 0 and not a band:** any band (±$1, ±0.1R) is arbitrary. Exactly 0 is objective.

  → [ADR 0011](decisions/0011-analytics-definitions.md)
- [ ] **Why is win rate wins / all trades, not wins / (wins + losses)?**
  - **The rates add up:** win rate + loss rate + breakeven rate = 1.
  - **Expectancy stays exactly the mean P/L.** The textbook `p(win) × avg win + p(loss) × avg loss` matches it because breakevens add 0, and a unit test asserts it.
  - **The alternative flatters the number:** 1 win, 1 loss and 8 scratches would show 50%.
- [ ] **What is expectancy, and why give it in R as well as dollars?**
  - **What it is:** the average result per trade. Positive means the system makes money over many trades, even with a low win rate (big winners, small losers).
  - **Why R too:** R normalizes by planned risk, so trades of different sizes compare. +0.33R per trade means each trade made a third of what it risked, on average.
  - **"Average R" and "expectancy in R" are the same number,** so the API returns it once.
- [ ] **How is max drawdown computed?**
  - **The method:** walk the cumulative P/L after each trade, tracking the running peak. The drawdown is the largest `peak − current`.
  - **The peak starts at 0,** so losing from the first trade counts.
  - **It's per trade, not per day,** so a same-day loss followed by a recovery isn't hidden. It uses the exact points the equity-curve endpoint returns.
  - **Cost:** O(n), one pass.
- [ ] **Why return `null` instead of 0 for an empty average?**
  - **They're different facts:** a 0% win rate means you lost every trade, while `null` means there's nothing to measure.
  - **Counts and totals are still 0,** because an empty sum really is 0.
  - **In C# terms,** it's `decimal?` vs `decimal`.
- [ ] **Why compute analytics in Python rather than SQL?**
  - **The brief:** it asks for pure functions with database-free unit tests.
  - **Drawdown:** it needs ordered, per-trade math.
  - **Scale:** one trader's data is small (hundreds of closed trades a year).
  - **The trade-off:** it loads the rows, where SQL `SUM` and `AVG` would push the work to the database.
  - **The escape hatch:** if a profile ever shows the loading is the bottleneck, the totals can move into SQL behind the same function signatures. Know the window-function version: `SUM(pnl) OVER (ORDER BY exit_at)` for the curve, then `MAX(...) OVER (...)` for the running peak.
- [ ] **What is the N+1 query problem, and where did you avoid it?**
  - **The problem:** load N parents with 1 query, then each one's children with 1 query apiece: N+1 round trips.
  - **Where I avoided it:** the weekly review loads every journal entry for the week's trades in one `WHERE trade_id IN (...)` query, then groups them in Python. That makes three queries per review, whatever the number of trades.
  - **The ORM alternative:** eager loading with `selectinload` (SQLAlchemy) or `.Include()` (EF Core).
- [ ] **How do you parse and validate an ISO week like `2026-W42`?**
  - **First a strict regex,** `\d{4}-W\d{2}`.
  - **Then `date.fromisocalendar(year, week, 1)`,** which rejects weeks that don't exist (W00, W54, W53 in a 52-week year). Both failures become a 422.
  - **The edge cases:**
    - The ISO year can differ from the calendar year: 2025-12-29 is in 2026-W01.
    - A year has 53 weeks when it starts on a Thursday, or on a Wednesday in a leap year.
  - **The window is Monday 00:00 UTC up to (not including) the next Monday:** half-open, so no instant falls in two weeks.
- [ ] **Why add a `cancelled_at` column instead of using `updated_at`?**
  - **`updated_at` means "last edited".** It moves when a cancelled trade's strategy is reassigned, which would move the trade into the wrong week.
  - **The migration has three parts:**
    1. it adds the nullable column
    2. it **backfills** the existing cancelled rows from `updated_at`, the best available estimate
    3. it extends the CHECK so the column is set exactly when the status is cancelled
  - **A test runs the migration over pre-existing rows.**

  → [ADR 0012](decisions/0012-weekly-review-and-cancelled-at.md)
- [ ] **Why does `Decimal("0.00000000")` serialize as `"0E-8"`, and why does it matter?**
  - **The cause:** Python's `str(Decimal)` uses exponent notation when the exponent is below -6.
  - **Why it matters:** the JSON was valid, but `decimal.Parse("0E-8")` in .NET throws without `NumberStyles.Float`, and humans misread it.
  - **The fix:** a reusable annotated type, `Annotated[Decimal, PlainSerializer(lambda d: format(d, "f"), when_used="json")]`, on every response decimal.
  - **The lesson:** test the boundary values (zero) of your output format, not only typical ones.

---

## Stage 6: Hardening

- [ ] **What is RFC 9457, and why use it for errors?**
  - **What it is:** "Problem Details for HTTP APIs", served as `application/problem+json`, with the fields `type`, `title`, `status`, `detail` and `instance`, plus any extension members (ours: `request_id`, `errors`).
  - **Why:** it's a standard that gateways and frameworks understand. ASP.NET Core's `ProblemDetails` is the same thing, and so is Spring's `ProblemDetail`.
  - **`type: about:blank`** means "no meaning beyond the status code". Specific type URIs can be added later without breaking clients.

  → [ADR 0013](decisions/0013-error-responses-and-pagination.md)
- [ ] **Why must validation errors not echo the input?**
  - **FastAPI's default 422 includes `input`,** the rejected value. For `/auth/register` that's the password.
  - **Where it would end up:** response bodies land in browser devtools, proxy logs and error trackers.
  - **What we keep:** only `loc`, `msg` and `type`. A test sends a short password and asserts it isn't anywhere in the response.
- [ ] **What should a 500 contain?**
  - **Nothing internal:** a generic message plus a request id.
  - **Why:** exception text can include SQL, file paths or data.
  - **Where the details go:** the logs, under the same request id. The client and the server each see what they need.
- [ ] **What is a request id, and how does yours work?**
  - **What it is:** a correlation id that is in the response header, the error body and every log line for that request.
  - **Ours:**
    - a client may send `X-Request-ID`, but only 1–64 characters of `[A-Za-z0-9._-]` are accepted, to prevent log injection
    - otherwise a UUID4 is generated
  - **In a microservice setup,** it would be forwarded to downstream calls. W3C `traceparent` and OpenTelemetry are the standard next step.
- [ ] **How do you keep secrets out of logs?**
  - **By construction:**
    - never log headers (tokens), bodies (passwords) or query strings
    - log extra fields only from an allowlist
    - create the engine with `hide_parameters=True`, so SQLAlchemy errors don't quote values like a password hash
  - **Proven by a test:** it exercises register, login, a failed login and a conflict, then searches the captured logs for the password, hash and token.

  → [ADR 0014](decisions/0014-structured-logging.md)
- [ ] **What is a `ContextVar`, and what's the threading gotcha?**
  - **What it is:** per-task (or per-thread) state that flows into child tasks. It's Python's equivalent of .NET's `AsyncLocal<T>`.
  - **The gotcha:** FastAPI runs sync dependencies in a thread pool with a *copy* of the context, so a value *set* there doesn't flow back to the middleware.
  - **The fix:** the ContextVar holds a mutable `RequestContext` object, and the dependency mutates the object.
- [ ] **Pure ASGI middleware vs `BaseHTTPMiddleware`?**
  - **`BaseHTTPMiddleware`** (`@app.middleware("http")`) is convenient, but it wraps the request and response in extra layers and has had edge cases with streaming and exceptions.
  - **A pure ASGI middleware** is a callable `(scope, receive, send)` that wraps `send` to see the status and add a header. It's small and predictable, and it can catch any exception to return a 500.
  - **The .NET parallel:** ASP.NET Core's `app.Use(async (ctx, next) => ...)` middleware.
- [ ] **Why are some lists paginated and others not?**
  - **Collections that grow without bound** (`/trades`) use keyset pagination (`items`, `next_cursor`).
  - **Small collections bounded by a parent or the user** (strategies, a trade's journal, breakdown groups) return plain arrays, so clients don't pay a cursor round trip for a case that can't happen.
  - **The rule is written down** (ADR 0013), so it's a convention, not an accident.
- [ ] **How did you shrink the Docker image, and why not Alpine?**
  - **The switch:** from Debian plus uv's standalone CPython (140 MB) to the official `python:3.15.0-slim-trixie`, copying only the locked venv into the runtime stage. That took 412 MB down to 290.
  - **Why not Alpine:** musl breaks the manylinux wheels (psycopg-binary, pydantic-core) and has DNS and performance quirks.
  - **Why not distroless:** it has no Python 3.15 yet and no shell for debugging.
  - **Keeping it small:** a CI job enforces a 300 MB budget.

  → [ADR 0015](decisions/0015-runtime-image.md)
- [ ] **Why run the container as non-root?**
  - **Limiting the damage:** if the app is compromised, the attacker doesn't get root in the container, which makes escaping to the host and tampering with files harder.
  - **The side effect:** the app can't write `.pyc` files, which is why bytecode is precompiled at build time.
  - **Kubernetes** (Phase 2) can then enforce `runAsNonRoot: true`.
- [ ] **Why a `HEALTHCHECK` in the image and `/health` vs `/ready`?**
  - **`/health` is liveness:** the process answers.
  - **`/ready` is readiness:** the database is reachable.
  - **Why it matters:** an orchestrator restarts a container that fails liveness, but only stops sending traffic to one that fails readiness. Restarting the API because Postgres blipped would make things worse.
  - **The image's `HEALTHCHECK`** probes liveness.
