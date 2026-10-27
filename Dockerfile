# syntax=docker/dockerfile:1

# Multi-stage, non-root, locked dependencies, on the official Python image (ADR 0015).
# Both stages use the same base, so the venv's interpreter link (/usr/local/bin/python3)
# resolves in the runtime stage too.

ARG PYTHON_IMAGE=python:3.15.0-slim-trixie

FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

# ---- builder: install the locked dependencies into /app/.venv ----
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3
WORKDIR /app

# Dependencies first, so this layer is reused until pyproject.toml or uv.lock change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# Then the project itself, installed as a regular (non-editable) package.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime: the base image plus the virtualenv, running as a non-root user ----
FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="trading-journal-api" \
      org.opencontainers.image.description="REST API for planning, logging and journaling swing trades" \
      org.opencontainers.image.source="https://github.com/MichaelRiehm/trading-journal-api"
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home --home-dir /app app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
# Migrations ship in the image, so the same image can run `alembic upgrade head`
# (the compose `migrate` service now; a Kubernetes Job in Phase 2).
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
# --no-access-log: the app writes its own JSON access line, with the request id (ADR 0014).
CMD ["uvicorn", "trading_journal.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
