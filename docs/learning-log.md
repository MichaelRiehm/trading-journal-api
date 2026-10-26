# Learning log

Dated entries, one per stage. Claude writes each entry at the end of the stage. Michael reviews them later, together with [interview-prep.md](interview-prep.md), which holds the study questions.

## 2026-10-12 — Stage 0: Scaffold

_Drafted by Claude. Not yet reviewed by Michael._

### What I built

- A uv project on Python 3.15 with a src layout.
- A FastAPI app with `GET /health` and a test.
- ruff, strict mypy and pre-commit.
- Postgres 18 and the API in Docker Compose.
- A Makefile and GitHub Actions CI.
- Branch protection on `main`.

The tooling choices are in [ADR 0001](decisions/0001-tooling.md).

### What I learned

- **Typing.** I thought mypy makes Python "strongly typed". Python is already strongly typed; what it lacks is *static* checking. mypy adds that, the way `tsc` does for JavaScript. Type hints do nothing at runtime unless a library like Pydantic or FastAPI reads them.
- **PyYAML.** I thought we'd "downgraded PyYAML to 3.14". Nothing was downgraded. PyYAML only lacked a prebuilt 3.15 wheel. It's a dependency of a dev tool (pre-commit), not of the app, so only that tool runs on 3.14.
- **uv.** The main value isn't "fewer tools". It's the lock file: the same exact packages on my laptop, in CI and in Docker.
- **src layout.** It's about testing the code as it's installed, not about third-party packages.

### What surprised me

- How much of the ecosystem lags a new Python release: PyYAML wheels, the official Docker image, and httpx being deprecated for Starlette's test client in favour of httpx2.
- Postgres 18 moved its data directory inside the Docker image, which breaks the classic volume mount.

### Bugs I hit and how I fixed them

- **CI failed at job setup.** `astral-sh/setup-uv@v10` didn't exist, because setup-uv publishes only full version tags. Fixed through #7 → #8 by pinning both actions to commit SHAs, which is also safer, since tags can be moved.
- **The Stage issues were created with off-by-one titles.** The PowerShell script that created them indexed an ordered hashtable by integer, which means by position, not by key. It went unnoticed for two weeks because only the issue numbers were checked. **Lesson:** verify what automation produced, not just that it ran.

### Interview talking point

"Before writing any code on a brand-new Python release, I checked every dependency for prebuilt 3.15 wheels on both Windows and Linux. One gap turned up, in a dev tool, so I isolated that tool on 3.14 instead of downgrading the whole project, and recorded it in an ADR with a trigger to revisit."
