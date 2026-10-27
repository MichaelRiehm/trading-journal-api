import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from trading_journal.api.deps import CurrentUser, TradeServiceDep
from trading_journal.api.errors import Responses
from trading_journal.schemas.pagination import Page
from trading_journal.schemas.trade import (
    TradeClose,
    TradeCreate,
    TradeListParams,
    TradeOpen,
    TradeRead,
    TradeUpdate,
)

router = APIRouter(prefix="/trades", tags=["trades"])

_NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Trade not found"}}
_ILLEGAL: Responses = {
    status.HTTP_409_CONFLICT: {"description": "Not allowed in the trade's current status"}
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Duplicate external_id for this source"}},
)
def create_trade(body: TradeCreate, user: CurrentUser, trades: TradeServiceDep) -> TradeRead:
    """Plan a trade. Every trade starts as `planned`."""
    return TradeRead.model_validate(trades.create(user.id, body))


@router.get("")
def list_trades(
    params: Annotated[TradeListParams, Query()], user: CurrentUser, trades: TradeServiceDep
) -> Page[TradeRead]:
    """Newest first. Pass `next_cursor` back as `cursor` for the next page."""
    items, next_cursor = trades.list(user.id, params)
    return Page[TradeRead](
        items=[TradeRead.model_validate(t) for t in items], next_cursor=next_cursor
    )


@router.get("/{trade_id}", responses=_NOT_FOUND)
def get_trade(trade_id: uuid.UUID, user: CurrentUser, trades: TradeServiceDep) -> TradeRead:
    return TradeRead.model_validate(trades.get(user.id, trade_id))


@router.patch("/{trade_id}", responses=_NOT_FOUND | _ILLEGAL)
def update_trade(
    trade_id: uuid.UUID, body: TradeUpdate, user: CurrentUser, trades: TradeServiceDep
) -> TradeRead:
    """Edit the plan (only while `planned`) or reassign the strategy (any status)."""
    return TradeRead.model_validate(trades.update(user.id, trade_id, body))


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND)
def delete_trade(trade_id: uuid.UUID, user: CurrentUser, trades: TradeServiceDep) -> None:
    trades.delete(user.id, trade_id)


@router.post("/{trade_id}/open", responses=_NOT_FOUND | _ILLEGAL)
def open_trade(
    trade_id: uuid.UUID, body: TradeOpen, user: CurrentUser, trades: TradeServiceDep
) -> TradeRead:
    """planned → open: record the actual entry."""
    return TradeRead.model_validate(trades.open(user.id, trade_id, body))


@router.post("/{trade_id}/close", responses=_NOT_FOUND | _ILLEGAL)
def close_trade(
    trade_id: uuid.UUID, body: TradeClose, user: CurrentUser, trades: TradeServiceDep
) -> TradeRead:
    """open → closed: record the exit. P/L, R-multiple and hold time appear in the response."""
    return TradeRead.model_validate(trades.close(user.id, trade_id, body))


@router.post("/{trade_id}/cancel", responses=_NOT_FOUND | _ILLEGAL)
def cancel_trade(trade_id: uuid.UUID, user: CurrentUser, trades: TradeServiceDep) -> TradeRead:
    """planned → cancelled: the setup was never taken. Kept for reviews."""
    return TradeRead.model_validate(trades.cancel(user.id, trade_id))
