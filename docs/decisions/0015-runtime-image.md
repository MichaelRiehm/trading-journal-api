# 0015: The runtime image on the official Python base

- **Status:** Accepted. It replaces the Stage 0 base-image workaround in ADR 0001.
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

**The Stage 0 base.** The Stage 0 image was built on `debian:trixie-slim`, with CPython 3.15.0 installed by uv, because the official `python:3.15-slim` image wasn't published yet (ADR 0001). It was already multi-stage and non-root.

**The size.** It weighed 412 MB (as `docker images` reports it on Docker Desktop). Most of that was uv's standalone CPython build (140 MB) next to the virtualenv (85 MB).

**What changed.** `python:3.15-slim` was published on 2026-10-24. Issue #6 asks to switch to it and reduce the image size.

## Decision

### The base

- **Both stages use `python:3.15.0-slim-trixie`,** pinned to the patch version and the Debian release, through one `ARG PYTHON_IMAGE`.
- **The builder still copies uv in** from `ghcr.io/astral-sh/uv:0.13.0`. It now uses the image's interpreter (`UV_PYTHON_DOWNLOADS=never`, `UV_PYTHON=/usr/local/bin/python3`) instead of downloading one.
- **The runtime stage copies in only the virtualenv,** at the same path. The venv's interpreter link (`/usr/local/bin/python3`) exists in both stages because they share a base.

### What stays from Stage 0

- **Multi-stage:** the build tools and the uv cache stay in the builder.
- **A non-root `app` user** (UID 999).
- **`uv sync --locked --no-dev`:** the exact locked runtime dependencies, with the project installed non-editable.
- **Bytecode precompiled at build time** (`UV_COMPILE_BYTECODE=1`, about 26 MB). As a non-root user the app can't write `.pyc` files next to the code, so without this every start would compile in memory again. `PYTHONDONTWRITEBYTECODE=1` stops it even trying.
- **Migrations and `alembic.ini` ship in the image,** so the same image runs `alembic upgrade head`. Tests and docs are excluded by `.dockerignore`.

### New

- **A `HEALTHCHECK` in the image** (a Python urllib probe of `/health`), so the image is health-aware outside compose too. Compose now relies on it instead of repeating it.
- **`--no-access-log`:** the app writes its own JSON access line (ADR 0014).
- **OCI labels:** title, description and source.
- **A CI job named `image`.** On every push it:
  - builds the image
  - fails if it runs as root (UID 0) or can't import the app
  - fails if the image is over **300 MB** (measured by `docker image inspect`)

  Branch protection still requires only `ci`, but a red `image` check shows up in review.

### The result

| | Before (Stage 0) | After |
|---|---|---|
| Base | `debian:trixie-slim` + uv CPython | `python:3.15.0-slim-trixie` |
| `docker images` (Docker Desktop) | 412 MB | 290 MB |
| `docker image inspect` | 392 MB | 277 MB |

That's about 30% smaller. The virtualenv (about 85 MB) is now the largest part we control.

## Alternatives considered

- **Keep the uv-managed CPython on Debian.** It works, but it's 140 MB of interpreter (headers, static libraries and the test suite included) where the official slim image ships a trimmed build. It also meant tracking a non-standard base.
- **Alpine (`python:3.15-alpine`).** It's smaller, but musl libc means no manylinux wheels for psycopg's binary build or pydantic-core. They'd be compiled in the builder or replaced, and musl has known DNS and performance differences. The savings don't justify the risk.
- **Distroless (`gcr.io/distroless/python3`).** It has a smaller attack surface, but it follows Debian's Python version (not 3.15) and has no shell, which makes `docker compose exec` debugging and the healthcheck harder. It's worth revisiting for Phase 2's Kubernetes images.
- **Dropping precompiled bytecode** to save about 26 MB. That's a slower start on every container launch, a bad trade for a service that restarts on deploy.
- **Pinning by digest** (`python:3.15.0-slim-trixie@sha256:…`). It's the most reproducible option, but without automation (Dependabot or Renovate) a digest pin silently stops receiving security patches. That's a Phase 2 item, together with image scanning.

## Consequences

- **The image follows the official Python release line,** with Debian security updates arriving through new `3.15.x-slim-trixie` tags.
- **A size or root regression fails CI** rather than going unnoticed.
- **ADR 0001's base-image note** is resolved by this ADR. ADR 0001 gets a dated status line pointing here.
- **The PyYAML follow-up from ADR 0001 is still open:** as of 2026-10-27, PyYAML 6.0.3 has no cp315 wheels, so pre-commit stays on Python 3.14.
