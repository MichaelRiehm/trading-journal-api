import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from trading_journal.domain.enums import AssetType, Side, TradeSource, TradeStatus
from trading_journal.models import Trade


@dataclass(frozen=True, slots=True)
class TradeFilters:
    """Optional equality filters for listing trades. None means "any"."""

    status: TradeStatus | None = None
    strategy_id: uuid.UUID | None = None
    symbol: str | None = None
    side: Side | None = None
    asset_type: AssetType | None = None
    source: TradeSource | None = None


class TradeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, trade: Trade) -> Trade:
        self._session.add(trade)
        self._session.flush()
        return trade

    def get(
        self, user_id: uuid.UUID, trade_id: uuid.UUID, *, for_update: bool = False
    ) -> Trade | None:
        """for_update locks the row until commit, so concurrent transitions run one at a time."""
        query = select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
        if for_update:
            query = query.with_for_update()
        return self._session.scalar(query)

    def list(
        self,
        user_id: uuid.UUID,
        filters: TradeFilters | None = None,
        *,
        limit: int | None = None,
        before_id: uuid.UUID | None = None,
    ) -> Sequence[Trade]:
        """Newest first. Keyset pagination: pass the last id seen as before_id (ADR 0009).

        UUIDv7 ids are time-ordered, so ordering by id is creation order and uses the
        primary key index.
        """
        query = select(Trade).where(Trade.user_id == user_id)
        f = filters or TradeFilters()
        for column, value in (
            (Trade.status, f.status),
            (Trade.strategy_id, f.strategy_id),
            (Trade.symbol, f.symbol),
            (Trade.side, f.side),
            (Trade.asset_type, f.asset_type),
            (Trade.source, f.source),
        ):
            if value is not None:
                query = query.where(column == value)
        if before_id is not None:
            query = query.where(Trade.id < before_id)
        query = query.order_by(Trade.id.desc())
        if limit is not None:
            query = query.limit(limit)
        return self._session.scalars(query).all()

    def save(self, trade: Trade) -> Trade:
        """Flush pending changes to a loaded trade, so constraint errors surface here."""
        self._session.flush()
        return trade

    def delete(self, trade: Trade) -> None:
        self._session.delete(trade)
        self._session.flush()
