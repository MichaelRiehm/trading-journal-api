import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute, Session

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
        query = _filtered(user_id, filters)
        if before_id is not None:
            query = query.where(Trade.id < before_id)
        query = query.order_by(Trade.id.desc())
        if limit is not None:
            query = query.limit(limit)
        return self._session.scalars(query).all()

    # --- analytics and reviews: [from, before) time windows, oldest first ----------

    def list_closed(
        self,
        user_id: uuid.UUID,
        filters: TradeFilters | None = None,
        *,
        exited_from: datetime | None = None,
        exited_before: datetime | None = None,
    ) -> Sequence[Trade]:
        """Closed trades in close order (exit_at, then id)."""
        query = _filtered(user_id, filters).where(Trade.status == TradeStatus.CLOSED)
        query = _window(query, Trade.exit_at, exited_from, exited_before)
        return self._session.scalars(query.order_by(Trade.exit_at, Trade.id)).all()

    def list_entered(
        self,
        user_id: uuid.UUID,
        filters: TradeFilters | None = None,
        *,
        entered_from: datetime | None = None,
        entered_before: datetime | None = None,
    ) -> Sequence[Trade]:
        """Trades that were opened (open or closed), in entry order."""
        query = _filtered(user_id, filters).where(Trade.entry_at.is_not(None))
        query = _window(query, Trade.entry_at, entered_from, entered_before)
        return self._session.scalars(query.order_by(Trade.entry_at, Trade.id)).all()

    def list_cancelled(
        self,
        user_id: uuid.UUID,
        *,
        cancelled_from: datetime | None = None,
        cancelled_before: datetime | None = None,
    ) -> Sequence[Trade]:
        query = select(Trade).where(Trade.user_id == user_id, Trade.status == TradeStatus.CANCELLED)
        query = _window(query, Trade.cancelled_at, cancelled_from, cancelled_before)
        return self._session.scalars(query.order_by(Trade.cancelled_at, Trade.id)).all()

    def save(self, trade: Trade) -> Trade:
        """Flush pending changes to a loaded trade, so constraint errors surface here."""
        self._session.flush()
        return trade

    def delete(self, trade: Trade) -> None:
        self._session.delete(trade)
        self._session.flush()


def _filtered(user_id: uuid.UUID, filters: TradeFilters | None) -> Select[Trade]:
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
    return query


def _window(
    query: Select[Trade],
    column: InstrumentedAttribute[datetime | None],
    start: datetime | None,
    before: datetime | None,
) -> Select[Trade]:
    if start is not None:
        query = query.where(column >= start)
    if before is not None:
        query = query.where(column < before)
    return query
