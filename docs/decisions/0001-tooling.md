# 0001: Tooling — uv, ruff, mypy, src layout

- **Status:** Accepted
- **Date:** 2026-10-12
- **Author:** Michael Riehm (reviewed with Claude)

## Context

We're building a production-style Python API as a portfolio project. I come from C#/.NET, so I want tooling that gives the guarantees I'm used to:

- reproducible builds
- type checking before the code runs
- one consistent set of commands

Development happens on Windows, while CI and Docker run on Linux. The brief targets Python 3.15, the newest release (out this month). Because it's so new, we had to check that every tool and library actually supports it before writing any code.

## Decision

- **uv** for Python itself, virtual environments, packages and locking.
  - It's essentially a bundle of the tools we need, so we don't need pyenv (Python versions), venv (isolated environments), pip (installing packages) or pip-tools (pinning versions).
  - The main benefit is the lock file. `pyproject.toml` lists what we depend on, and `uv.lock` pins the exact version of every package, including dependencies of dependencies.
  - My laptop, CI and the Docker image all install from the same lock, and `uv sync --locked` fails if the lock is out of date.
- **ruff** for linting and formatting. It's an all-in-one replacement like uv; both are made by Astral.
  - It replaces black (formatting), isort (import order) and flake8 with its plugins (linting).
  - Linting catches likely bugs and security problems. Formatting keeps the layout consistent.
  - It's fast enough to run on every save and every commit.
- **mypy in strict mode** for static type checking.
  - Python is already strongly typed (`"1" + 1` is an error), but it's dynamically typed: types are only checked while the code runs, and Python ignores type hints at runtime.
  - mypy checks the type hints before the code runs, much like the TypeScript compiler does for JavaScript. Strict mode requires every function to be annotated.
  - Pydantic covers the runtime side, by validating data where it enters the API.
- **src layout.** Our code lives in `src/trading_journal/`, so Python can't import it just because it's in the current folder; it has to be installed (uv installs it in editable mode). Tests import our package the same way production does, so packaging mistakes show up in tests instead of after deployment.
- **A Makefile** for the common commands (up, down, test, lint, format, typecheck). CI runs the same targets, so local runs and CI runs execute identical commands.
- **pre-commit** runs ruff, mypy and `uv lock --check` before every commit, through `uv run`, so the hooks use the same versions as CI.
- **httpx2** as the library behind FastAPI's `TestClient`. Starlette (the framework underneath FastAPI) now prefers it and warns when it falls back to httpx. httpx2 is httpx's successor, by the same author.

## Alternatives considered

- **pip + venv + pip-tools (+ pyenv).** The traditional setup: four tools to do what uv does, much slower, and Python versions are managed separately.
- **Poetry.** Mature and popular, but slower and doesn't install Python itself. It also used its own dependency format instead of the standard `[project]` table until version 2.0.
- **black + isort + flake8.** Three tools and three configs. ruff does all three jobs and formats the same way black does.
- **pyright.** A strong type checker that powers Pylance in VS Code. We chose mypy as the long-standing reference checker, with a plugin that understands Pydantic models. Pyright can still run in the editor.
- **Flat layout** (the package at the repo root). Tests could import the source folder directly and pass even when the installed package is broken.
- **just or taskipy instead of make.** Both work. make is the most widely known and comes preinstalled on CI runners; on Windows it's one `winget install ezwinports.make`.
- **Keeping httpx** (named in the brief). It works today, but Starlette has deprecated it for `TestClient`, so we'd get a warning now and a forced migration later.
- **Moving the whole project to Python 3.14.** The brief allows this if a dependency has no 3.15 wheel. It wasn't needed: the only gap was in a dev tool, not in the app (see Consequences).

## Consequences

- **Python 3.15 support.**
  - Before writing code, we checked that every dependency has a prebuilt package (a wheel) for 3.15 on Windows and Linux. All of the app's dependencies do.
  - The one gap: PyYAML has no 3.15 wheel yet. PyYAML isn't one of our dependencies; pre-commit needs it.
  - Instead of moving the project to 3.14, we installed pre-commit as a separate tool on Python 3.14 (`uv tool install pre-commit --python 3.14`, like `dotnet tool install -g`).
  - The project still runs entirely on 3.15, and the checks pre-commit runs (ruff, mypy) still use the project's 3.15 environment.
  - Revisit when PyYAML ships 3.15 wheels.
- **No official `python:3.15-slim` Docker image yet**, only release candidates. The Dockerfile uses `debian:trixie-slim` and installs the same Python 3.15.0 build through uv. Revisit in Stage 6. _Update 2026-10-26: `python:3.15-slim` was published on 2026-10-24. The switch is tracked in #6._
- **httpx2 wheels have no PyPI provenance attestation yet.** Trust rests on the maintainers (httpx's original author, under the pydantic GitHub org) and on Starlette recommending it. `PROJECT_BRIEF.md` was updated to name httpx2.
- **Strict mypy means more annotations up front,** in exchange for catching type errors before tests run.
- **Contributors need uv, Docker and make installed.** pre-commit is optional but recommended.
