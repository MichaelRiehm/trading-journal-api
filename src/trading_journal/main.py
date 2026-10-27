"""Application entry point: builds the FastAPI app and wires up the routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from trading_journal.api import auth, health, strategies, trades, users
from trading_journal.api.errors import register_error_handlers
from trading_journal.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail at startup, not on the first request, if settings (e.g. JWT_SECRET_KEY) are bad.
    get_settings()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trading Journal API",
        summary="Plan, log and journal swing trades, with analytics and weekly reviews.",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(strategies.router)
    app.include_router(trades.router)
    return app


# uvicorn imports this module-level instance: `uvicorn trading_journal.main:app`
app = create_app()
