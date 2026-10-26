import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from trading_journal.models import Strategy


class StrategyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, user_id: uuid.UUID, name: str, description: str | None = None) -> Strategy:
        strategy = Strategy(user_id=user_id, name=name, description=description)
        self._session.add(strategy)
        self._session.flush()
        return strategy

    def get(self, user_id: uuid.UUID, strategy_id: uuid.UUID) -> Strategy | None:
        return self._session.scalar(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user_id)
        )

    def list(self, user_id: uuid.UUID) -> Sequence[Strategy]:
        return self._session.scalars(
            select(Strategy).where(Strategy.user_id == user_id).order_by(Strategy.name)
        ).all()

    def delete(self, strategy: Strategy) -> None:
        self._session.delete(strategy)
        self._session.flush()
