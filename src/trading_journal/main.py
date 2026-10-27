"""Application entry point: builds the FastAPI app and wires up the routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from trading_journal.api import analytics, auth, health, journal, reviews, strategies, trades, users
from trading_journal.api.errors import APP_RESPONSES, install_openapi, register_error_handlers
from trading_journal.api.middleware import RequestContextMiddleware
from trading_journal.config import get_settings
from trading_journal.logging_config import LoggingSettings, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail at startup, not on the first request, if settings (e.g. JWT_SECRET_KEY) are bad.
    get_settings()
    yield


def create_app() -> FastAPI:
    # At import, not in lifespan: uvicorn has already set up its loggers by then, and its
    # startup lines should come out as JSON too.
    configure_logging(LoggingSettings().log_level)
    app = FastAPI(
        title="Trading Journal API",
        summary="Plan, log and journal swing trades, with analytics and weekly reviews.",
        version="0.1.0",
        lifespan=lifespan,
        responses=APP_RESPONSES,
    )
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    install_openapi(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(strategies.router)
    app.include_router(trades.router)
    app.include_router(journal.trade_journal_router)
    app.include_router(journal.entry_router)
    app.include_router(analytics.router)
    app.include_router(reviews.router)
    return app


# uvicorn imports this module-level instance: `uvicorn trading_journal.main:app`
app = create_app()
