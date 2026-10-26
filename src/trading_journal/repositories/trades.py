import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from trading_journal.models import Trade


class TradeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, trade: Trade) -> Trade:
        self._session.add(trade)
        self._session.flush()
        return trade

    def get(self, user_id: uuid.UUID, trade_id: uuid.UUID) -> Trade | None:
        return self._session.scalar(
            select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
        )

    def list(self, user_id: uuid.UUID) -> Sequence[Trade]:
        # Filters and pagination arrive with the trades API (Stage 3).
        return self._session.scalars(
            select(Trade).where(Trade.user_id == user_id).order_by(Trade.created_at.desc())
        ).all()

    def save(self, trade: Trade) -> Trade:
        """Flush pending changes to a loaded trade, so constraint errors surface here."""
        self._session.flush()
        return trade

    def delete(self, trade: Trade) -> None:
        self._session.delete(trade)
        self._session.flush()
