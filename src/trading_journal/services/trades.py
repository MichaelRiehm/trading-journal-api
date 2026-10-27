import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trading_journal.domain import lifecycle, trade_rules
from trading_journal.domain.enums import TradeStatus
from trading_journal.domain.errors import ConflictError, InvalidInputError, NotFoundError
from trading_journal.models import Trade
from trading_journal.repositories import StrategyRepository, TradeRepository
from trading_journal.repositories.trades import TradeFilters
from trading_journal.schemas.trade import (
    PLAN_FIELDS,
    TradeClose,
    TradeCreate,
    TradeListParams,
    TradeOpen,
    TradeUpdate,
)
from trading_journal.services._db_errors import violated_constraint

# Backfilling past trades is fine; a time in the future is a typo or a clock problem.
# A little slack absorbs clock skew between the client and the server.
_FUTURE_SLACK = timedelta(minutes=5)


class TradeService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._trades = TradeRepository(session)
        self._strategies = StrategyRepository(session)

    # --- queries ---------------------------------------------------------------

    def get(self, user_id: uuid.UUID, trade_id: uuid.UUID, *, for_update: bool = False) -> Trade:
        trade = self._trades.get(user_id, trade_id, for_update=for_update)
        if trade is None:
            raise NotFoundError("Trade")
        return trade

    def list(
        self, user_id: uuid.UUID, params: TradeListParams
    ) -> tuple[Sequence[Trade], uuid.UUID | None]:
        """Return one page of trades, newest first, and the cursor for the next page."""
        filters = TradeFilters(
            status=params.status,
            strategy_id=params.strategy_id,
            symbol=params.symbol,
            side=params.side,
            asset_type=params.asset_type,
            source=params.source,
        )
        # Fetch one extra row to learn whether another page exists.
        rows = self._trades.list(user_id, filters, limit=params.limit + 1, before_id=params.cursor)
        page = rows[: params.limit]
        next_cursor = page[-1].id if len(rows) > params.limit else None
        return page, next_cursor

    # --- the plan ---------------------------------------------------------------

    def create(self, user_id: uuid.UUID, data: TradeCreate) -> Trade:
        self._ensure_own_strategy(user_id, data.strategy_id)
        trade_rules.check_plan(
            side=data.side,
            planned_entry=data.planned_entry,
            planned_stop=data.planned_stop,
            asset_type=data.asset_type,
            leverage_factor=data.leverage_factor,
        )
        try:
            trade = self._trades.add(Trade(user_id=user_id, **data.model_dump()))
        except IntegrityError as exc:
            self._session.rollback()
            if violated_constraint(exc) == "uq_trades_user_id_source_external_id":
                raise ConflictError(
                    "A trade with this external_id already exists for this source"
                ) from exc
            raise
        self._session.commit()
        return trade

    def update(self, user_id: uuid.UUID, trade_id: uuid.UUID, data: TradeUpdate) -> Trade:
        trade = self.get(user_id, trade_id, for_update=True)
        changes = data.model_dump(exclude_unset=True)
        if changes.keys() & PLAN_FIELDS and not lifecycle.plan_is_editable(trade.status):
            raise ConflictError(
                f"The plan can only be changed while the trade is planned, not {trade.status}"
            )
        if "strategy_id" in changes:
            self._ensure_own_strategy(user_id, changes["strategy_id"])

        # Validate the merged result before touching the trade, so a rejected PATCH
        # leaves nothing dirty in the session.
        merged: dict[str, Any] = {
            field: changes.get(field, getattr(trade, field))
            for field in ("side", "planned_entry", "planned_stop", "asset_type", "leverage_factor")
        }
        trade_rules.check_plan(**merged)

        for field, value in changes.items():
            setattr(trade, field, value)
        self._trades.save(trade)
        self._session.commit()
        return trade

    def delete(self, user_id: uuid.UUID, trade_id: uuid.UUID) -> None:
        self._trades.delete(self.get(user_id, trade_id))
        self._session.commit()

    # --- lifecycle (ADR 0008) ---------------------------------------------------
    # Each transition locks the row (SELECT ... FOR UPDATE), so two concurrent
    # requests for the same trade run one after the other and the second sees the
    # new status.

    def open(self, user_id: uuid.UUID, trade_id: uuid.UUID, data: TradeOpen) -> Trade:
        trade = self.get(user_id, trade_id, for_update=True)
        lifecycle.ensure_can_transition(trade.status, TradeStatus.OPEN)
        entry_at = self._not_in_future(data.entry_at, "entry_at")

        trade.entry_price = data.entry_price
        trade.quantity = data.quantity
        trade.entry_at = entry_at
        trade.status = TradeStatus.OPEN
        return self._commit(trade)

    def close(self, user_id: uuid.UUID, trade_id: uuid.UUID, data: TradeClose) -> Trade:
        trade = self.get(user_id, trade_id, for_update=True)
        lifecycle.ensure_can_transition(trade.status, TradeStatus.CLOSED)
        exit_at = self._not_in_future(data.exit_at, "exit_at")
        if trade.entry_at is not None and exit_at < trade.entry_at:
            raise InvalidInputError("exit_at cannot be before entry_at")

        trade.exit_price = data.exit_price
        trade.exit_at = exit_at
        trade.fees = data.fees
        trade.followed_plan = data.followed_plan
        trade.status = TradeStatus.CLOSED
        return self._commit(trade)

    def cancel(self, user_id: uuid.UUID, trade_id: uuid.UUID) -> Trade:
        trade = self.get(user_id, trade_id, for_update=True)
        lifecycle.ensure_can_transition(trade.status, TradeStatus.CANCELLED)
        trade.status = TradeStatus.CANCELLED
        return self._commit(trade)

    # --- helpers -----------------------------------------------------------------

    def _ensure_own_strategy(self, user_id: uuid.UUID, strategy_id: uuid.UUID | None) -> None:
        # The same message whether the strategy is missing or someone else's: no id leaks.
        if strategy_id is not None and self._strategies.get(user_id, strategy_id) is None:
            raise InvalidInputError("strategy_id does not match any of your strategies")

    @staticmethod
    def _not_in_future(moment: datetime | None, field: str) -> datetime:
        now = datetime.now(UTC)
        if moment is None:
            return now
        if moment > now + _FUTURE_SLACK:
            raise InvalidInputError(f"{field} cannot be in the future")
        return moment

    def _commit(self, trade: Trade) -> Trade:
        self._trades.save(trade)
        self._session.commit()
        return trade
