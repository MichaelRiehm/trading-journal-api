"""Analytics over a user's closed trades. The math is in domain/analytics.py (ADR 0011).

This service only loads the trades, turns them into `ClosedTrade` values with the same
`calculations` functions the trade responses use, and hands them to the pure functions.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

from trading_journal.domain import analytics, calculations
from trading_journal.models import Trade
from trading_journal.repositories import StrategyRepository, TradeRepository
from trading_journal.repositories.trades import TradeFilters
from trading_journal.schemas.analytics import AnalyticsParams, BreakdownBy, BreakdownParams


@dataclass(frozen=True, slots=True)
class BreakdownGroup:
    key: str | None
    label: str
    summary: analytics.Summary


def closed_trade(trade: Trade) -> analytics.ClosedTrade:
    """The analytics view of a closed trade: its P/L, R and hold time, computed once."""
    if (
        trade.entry_price is None
        or trade.entry_at is None
        or trade.quantity is None
        or trade.exit_price is None
        or trade.exit_at is None
        or trade.fees is None
        or trade.followed_plan is None
    ):
        # The status_fields CHECK constraint makes this unreachable for a closed trade.
        raise ValueError(f"trade {trade.id} is not closed")
    pnl = calculations.pnl(
        trade.side, trade.entry_price, trade.exit_price, trade.quantity, trade.fees
    )
    risk = calculations.r_per_share(trade.planned_entry, trade.planned_stop)
    return analytics.ClosedTrade(
        trade_id=trade.id,
        exit_at=trade.exit_at,
        pnl=pnl,
        r_multiple=calculations.r_multiple(pnl, trade.quantity, risk),
        fees=trade.fees,
        hold_time=calculations.hold_time(trade.entry_at, trade.exit_at),
        followed_plan=trade.followed_plan,
    )


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self._trades = TradeRepository(session)
        self._strategies = StrategyRepository(session)

    def summary(self, user_id: uuid.UUID, params: AnalyticsParams) -> analytics.Summary:
        return analytics.summarize(self._closed(user_id, params))

    def equity_curve(
        self, user_id: uuid.UUID, params: AnalyticsParams
    ) -> list[analytics.EquityPoint]:
        return analytics.equity_curve(self._closed(user_id, params))

    def breakdown(self, user_id: uuid.UUID, params: BreakdownParams) -> list[BreakdownGroup]:
        """The summary per group, the biggest groups first."""
        key_of, label_of = self._grouping(user_id, params.by)
        groups: defaultdict[str | None, list[analytics.ClosedTrade]] = defaultdict(list)
        for trade in self._closed_trades(user_id, params):
            groups[key_of(trade)].append(closed_trade(trade))
        result = [
            BreakdownGroup(key, label_of(key), analytics.summarize(trades))
            for key, trades in groups.items()
        ]
        return sorted(result, key=lambda g: (-g.summary.trade_count, g.label))

    def frequency(self, user_id: uuid.UUID, params: AnalyticsParams) -> list[analytics.WeekCount]:
        """Trades opened per ISO week (by entry_at), empty weeks included."""
        start, before = _utc_window(params.start_date, params.end_date)
        trades = self._trades.list_entered(
            user_id, _filters(params), entered_from=start, entered_before=before
        )
        days = [t.entry_at.astimezone(UTC).date() for t in trades if t.entry_at is not None]
        return analytics.weekly_counts(days, params.start_date, params.end_date)

    # --- helpers -----------------------------------------------------------------

    def _closed_trades(self, user_id: uuid.UUID, params: AnalyticsParams) -> Sequence[Trade]:
        start, before = _utc_window(params.start_date, params.end_date)
        return self._trades.list_closed(
            user_id, _filters(params), exited_from=start, exited_before=before
        )

    def _closed(self, user_id: uuid.UUID, params: AnalyticsParams) -> list[analytics.ClosedTrade]:
        return [closed_trade(t) for t in self._closed_trades(user_id, params)]

    def _grouping(
        self, user_id: uuid.UUID, by: BreakdownBy
    ) -> tuple[Callable[[Trade], str | None], Callable[[str | None], str]]:
        """How to get a trade's group key, and how to label a key for display."""
        if by is BreakdownBy.STRATEGY:
            names = {str(k): v for k, v in self._strategies.names(user_id).items()}
            return (
                lambda t: str(t.strategy_id) if t.strategy_id else None,
                lambda key: names[key] if key else "No strategy",
            )
        key_of: dict[BreakdownBy, Callable[[Trade], str]] = {
            BreakdownBy.SYMBOL: lambda t: t.symbol,
            BreakdownBy.SIDE: lambda t: t.side.value,
            BreakdownBy.ASSET_TYPE: lambda t: t.asset_type.value,
            BreakdownBy.EXPOSURE: lambda t: calculations.exposure(t.side, t.leverage_factor).value,
        }
        return key_of[by], lambda key: key or ""


def _filters(params: AnalyticsParams) -> TradeFilters:
    return TradeFilters(
        strategy_id=params.strategy_id,
        symbol=params.symbol,
        side=params.side,
        asset_type=params.asset_type,
        source=params.source,
    )


def _utc_window(start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    """Inclusive dates to a [from, before) window in UTC: end_date covers its whole day."""
    begin = datetime.combine(start, time(), tzinfo=UTC) if start else None
    before = datetime.combine(end + timedelta(days=1), time(), tzinfo=UTC) if end else None
    return begin, before
