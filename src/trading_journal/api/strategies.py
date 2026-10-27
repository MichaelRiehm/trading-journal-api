import uuid

from fastapi import APIRouter, status

from trading_journal.api.deps import CurrentUser, StrategyServiceDep
from trading_journal.api.errors import UNAUTHORIZED, problem
from trading_journal.schemas.strategy import StrategyCreate, StrategyRead, StrategyUpdate

router = APIRouter(prefix="/strategies", tags=["strategies"], responses=UNAUTHORIZED)

_NOT_FOUND = problem(status.HTTP_404_NOT_FOUND, "Strategy not found")
_CONFLICT = problem(status.HTTP_409_CONFLICT, "Duplicate name, or the strategy has trades")


@router.post("", status_code=status.HTTP_201_CREATED, responses=_CONFLICT)
def create_strategy(
    body: StrategyCreate, user: CurrentUser, strategies: StrategyServiceDep
) -> StrategyRead:
    return StrategyRead.model_validate(strategies.create(user.id, body))


@router.get("")
def list_strategies(user: CurrentUser, strategies: StrategyServiceDep) -> list[StrategyRead]:
    return [StrategyRead.model_validate(s) for s in strategies.list(user.id)]


@router.get("/{strategy_id}", responses=_NOT_FOUND)
def get_strategy(
    strategy_id: uuid.UUID, user: CurrentUser, strategies: StrategyServiceDep
) -> StrategyRead:
    return StrategyRead.model_validate(strategies.get(user.id, strategy_id))


@router.patch("/{strategy_id}", responses=_NOT_FOUND | _CONFLICT)
def update_strategy(
    strategy_id: uuid.UUID, body: StrategyUpdate, user: CurrentUser, strategies: StrategyServiceDep
) -> StrategyRead:
    return StrategyRead.model_validate(strategies.update(user.id, strategy_id, body))


@router.delete(
    "/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND | _CONFLICT
)
def delete_strategy(
    strategy_id: uuid.UUID, user: CurrentUser, strategies: StrategyServiceDep
) -> None:
    strategies.delete(user.id, strategy_id)
