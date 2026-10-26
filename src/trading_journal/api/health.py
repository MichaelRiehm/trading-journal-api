"""Probes. `/health` is liveness (the process is up); `/ready` checks the database."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from trading_journal.db.session import database_is_reachable, get_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "unavailable"]


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
def ready(session: Annotated[Session, Depends(get_session)], response: Response) -> ReadyResponse:
    # Plain `def`: the database call blocks, so FastAPI runs it on its thread pool.
    if database_is_reachable(session):
        return ReadyResponse(status="ready")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="unavailable")
