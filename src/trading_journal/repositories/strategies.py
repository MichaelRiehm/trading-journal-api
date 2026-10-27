import uuid
from collections.abc import Sequence

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from trading_journal.models import Strategy, Trade


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

    def names(self, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
        rows = self._session.execute(
            select(Strategy.id, Strategy.name).where(Strategy.user_id == user_id)
        )
        return dict(rows.all())

    def get_by_name(self, user_id: uuid.UUID, name: str) -> Strategy | None:
        return self._session.scalar(
            select(Strategy).where(Strategy.user_id == user_id, Strategy.name == name)
        )

    def has_trades(self, user_id: uuid.UUID, strategy_id: uuid.UUID) -> bool:
        query = select(Trade.id).where(Trade.user_id == user_id, Trade.strategy_id == strategy_id)
        return self._session.scalar(select(exists(query))) is True

    def save(self, strategy: Strategy) -> Strategy:
        """Flush pending changes to a loaded strategy, so constraint errors surface here."""
        self._session.flush()
        return strategy

    def delete(self, strategy: Strategy) -> None:
        self._session.delete(strategy)
        self._session.flush()
