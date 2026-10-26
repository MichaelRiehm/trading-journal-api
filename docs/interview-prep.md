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
