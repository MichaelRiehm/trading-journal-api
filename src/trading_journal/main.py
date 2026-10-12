"""Application entry point: builds the FastAPI app and wires up the routers."""

from fastapi import FastAPI

from trading_journal.api import health


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trading Journal API",
        summary="Plan, log and journal swing trades, with analytics and weekly reviews.",
        version="0.1.0",
    )
    app.include_router(health.router)
    return app


# uvicorn imports this module-level instance: `uvicorn trading_journal.main:app`
app = create_app()
