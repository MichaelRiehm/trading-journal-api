# syntax=docker/dockerfile:1

# Stage 0 image: multi-stage, non-root, locked dependencies. Stage 6 finalizes it.
# The base is debian:trixie-slim plus uv-managed CPython 3.15.0, because the official
# python:3.15-slim image is not published yet (see docs/decisions/0001-tooling.md).

FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

# ---- builder: install Python and the locked dependencies into /app/.venv ----
FROM debian:trixie-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed
WORKDIR /app

COPY .python-version ./
RUN uv python install

# Dependencies first, so this layer is reused until pyproject.toml or uv.lock change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# Then the project itself, installed as a regular (non-editable) package.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime: just the interpreter and the virtualenv, running as a non-root user ----
FROM debian:trixie-slim AS runtime
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home --home-dir /app app
COPY --from=builder /python /python
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
# Migrations ship in the image, so the same image can run `alembic upgrade head`
# (the compose `migrate` service now; a Kubernetes Job in Phase 2).
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "trading_journal.main:app", "--host", "0.0.0.0", "--port", "8000"]
