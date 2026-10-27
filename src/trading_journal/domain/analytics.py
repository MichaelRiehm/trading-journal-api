"""Analytics math: pure functions over closed trades. No database, no floats.

Definitions are in ADR 0011. In short:
- A trade's outcome is the sign of its net P/L (after fees); exactly 0 is breakeven.
- Rates divide by all closed trades, so breakevens count in the denominator.
- Expectancy is the mean P/L (and mean R) over all closed trades.
- Max drawdown is the largest fall from a peak of the per-trade cumulative P/L,
  where the curve starts at 0.
- A value that is undefined for the trades given (an average of nothing) is None, not 0.
"""

import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum

from trading_journal.domain.calculations import MONEY_QUANTUM, R_QUANTUM
from trading_journal.domain.iso_week import week_start

RATE_QUANTUM = Decimal("0.0001")  # rates are fractions: 0.6667 is 66.67%

_PRECISION = 50
_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """What analytics needs from a closed trade, already computed by `calculations`."""

    trade_id: uuid.UUID
    exit_at: datetime
    pnl: Decimal
    r_multiple: Decimal
    fees: Decimal
    hold_time: timedelta
    followed_plan: bool


class Outcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


def outcome(pnl: Decimal) -> Outcome:
    if pnl > 0:
        return Outcome.WIN
    if pnl < 0:
        return Outcome.LOSS
    return Outcome.BREAKEVEN


@dataclass(frozen=True, slots=True)
class Summary:
    trade_count: int
    wins: int
    losses: int
    breakevens: int
    win_rate: Decimal | None
    expectancy: Decimal | None  # mean net P/L per trade, in dollars
    expectancy_r: Decimal | None  # mean R-multiple per trade ("average R")
    average_win: Decimal | None
    average_loss: Decimal | None  # negative
    average_win_r: Decimal | None
    average_loss_r: Decimal | None  # negative
    total_pnl: Decimal
    total_fees: Decimal
    largest_win: Decimal | None
    largest_loss: Decimal | None  # the most negative P/L
    average_hold_time: timedelta | None
    average_hold_time_winners: timedelta | None
    average_hold_time_losers: timedelta | None
    plan_adherence_rate: Decimal | None
    max_drawdown: Decimal  # positive dollars; 0 if the curve never fell


@dataclass(frozen=True, slots=True)
class EquityPoint:
    trade_id: uuid.UUID
    exit_at: datetime
    pnl: Decimal
    cumulative_pnl: Decimal


@dataclass(frozen=True, slots=True)
class WeekCount:
    week_start: date  # the Monday
    count: int


def chronological(trades: Iterable[ClosedTrade]) -> list[ClosedTrade]:
    """Close order. The UUIDv7 id breaks ties between trades closed at the same instant."""
    return sorted(trades, key=lambda t: (t.exit_at, t.trade_id))


def summarize(trades: Iterable[ClosedTrade]) -> Summary:
    ordered = chronological(trades)
    wins = [t for t in ordered if outcome(t.pnl) is Outcome.WIN]
    losses = [t for t in ordered if outcome(t.pnl) is Outcome.LOSS]
    count = len(ordered)
    return Summary(
        trade_count=count,
        wins=len(wins),
        losses=len(losses),
        breakevens=count - len(wins) - len(losses),
        win_rate=ratio(len(wins), count),
        expectancy=mean([t.pnl for t in ordered], MONEY_QUANTUM),
        expectancy_r=mean([t.r_multiple for t in ordered], R_QUANTUM),
        average_win=mean([t.pnl for t in wins], MONEY_QUANTUM),
        average_loss=mean([t.pnl for t in losses], MONEY_QUANTUM),
        average_win_r=mean([t.r_multiple for t in wins], R_QUANTUM),
        average_loss_r=mean([t.r_multiple for t in losses], R_QUANTUM),
        total_pnl=_money(_sum(t.pnl for t in ordered)),
        total_fees=_money(_sum(t.fees for t in ordered)),
        largest_win=max((t.pnl for t in wins), default=None),
        largest_loss=min((t.pnl for t in losses), default=None),
        average_hold_time=mean_duration([t.hold_time for t in ordered]),
        average_hold_time_winners=mean_duration([t.hold_time for t in wins]),
        average_hold_time_losers=mean_duration([t.hold_time for t in losses]),
        plan_adherence_rate=ratio(sum(t.followed_plan for t in ordered), count),
        max_drawdown=max_drawdown(equity_curve(ordered)),
    )


def equity_curve(trades: Iterable[ClosedTrade]) -> list[EquityPoint]:
    """Cumulative net P/L after each trade, in close order."""
    points: list[EquityPoint] = []
    running = _ZERO
    with localcontext(prec=_PRECISION):
        for t in chronological(trades):
            running += t.pnl
            points.append(EquityPoint(t.trade_id, t.exit_at, t.pnl, running))
    return points


def max_drawdown(curve: Sequence[EquityPoint]) -> Decimal:
    """The largest fall from a running peak to a later point. The peak starts at 0,
    so losing from the first trade on is a drawdown too."""
    peak = worst = _ZERO
    with localcontext(prec=_PRECISION):
        for point in curve:
            peak = max(peak, point.cumulative_pnl)
            worst = max(worst, peak - point.cumulative_pnl)
    return _money(worst)


def weekly_counts(
    days: Iterable[date], first_week: date | None = None, last_week: date | None = None
) -> list[WeekCount]:
    """How many of `days` fall in each ISO week, with empty weeks filled in as 0.

    The weeks run from first_week to last_week (any day in them); when one is missing,
    the earliest or latest day given stands in for it. Nothing at all gives [].
    """
    counts = Counter(week_start(day) for day in days)
    first = week_start(first_week) if first_week else min(counts, default=None)
    last = week_start(last_week) if last_week else max(counts, default=None)
    first = first or last
    last = last or first
    if first is None or last is None:
        return []
    weeks: list[WeekCount] = []
    monday = first
    while monday <= last:
        weeks.append(WeekCount(monday, counts[monday]))
        monday += timedelta(weeks=1)
    return weeks


# --- helpers --------------------------------------------------------------------


def mean(values: Sequence[Decimal], quantum: Decimal) -> Decimal | None:
    if not values:
        return None
    with localcontext(prec=_PRECISION):
        return (_sum(values) / len(values)).quantize(quantum, rounding=ROUND_HALF_EVEN)


def ratio(part: int, whole: int) -> Decimal | None:
    if whole == 0:
        return None
    with localcontext(prec=_PRECISION):
        return (Decimal(part) / whole).quantize(RATE_QUANTUM, rounding=ROUND_HALF_EVEN)


def mean_duration(values: Sequence[timedelta]) -> timedelta | None:
    if not values:
        return None
    return sum(values, timedelta()) / len(values)


def _sum(values: Iterable[Decimal]) -> Decimal:
    with localcontext(prec=_PRECISION):
        return sum(values, _ZERO)


def _money(value: Decimal) -> Decimal:
    # Sums of 8-dp values are exact; this only fixes the scale, so 0 prints as 0.00000000.
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)
