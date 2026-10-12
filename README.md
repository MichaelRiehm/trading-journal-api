# Trading Journal API

A REST API where a swing trader plans trades before entering, logs the result, journals thoughts before, during and after each trade, and gets analytics plus a weekly review of habits.

**Status:** Stage 0 (scaffold). Only `GET /health` exists so far. See [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the full scope and stage plan.

## Stack

Python 3.15 · FastAPI · Pydantic v2 · SQLAlchemy 2.1 · Alembic · psycopg 3 · PostgreSQL 18 · uv · ruff · mypy · pytest · Docker Compose · GitHub Actions

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker, GNU make.

```sh
uv sync                        # install Python deps into .venv from uv.lock
cp .env.example .env           # local settings (gitignored)
make up                        # Postgres 18 + the API, waits until healthy
curl http://localhost:8000/health
make down
```

Interactive API docs: http://localhost:8000/docs

## Development

```sh
make test        # pytest
make lint        # ruff check + format check
make format      # apply formatting and safe fixes
make typecheck   # mypy --strict
```

Git hooks: `uv tool install pre-commit --python 3.14`, then `pre-commit install`.

## Architecture

Layered: router → service → repository. Details in [CLAUDE.md](CLAUDE.md) and [PROJECT_BRIEF.md](PROJECT_BRIEF.md).

## Decisions

- [0001: Tooling (uv, ruff, mypy, src layout)](docs/decisions/0001-tooling.md)

Learning log: [docs/learning-log.md](docs/learning-log.md)
