"""Unit tests for the analytics math. Pure functions: no database (ADR 0011)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from trading_journal.domain import analytics, calculations
from trading_journal.domain.analytics import ClosedTrade, Outcome, WeekCount
from trading_journal.domain.enums import Side

_START = datetime(2026, 10, 5, 20, 0, tzinfo=UTC)


def trade(
    pnl: str,
    r: str | None = None,
    *,
    day: int = 0,
    fees: str = "0",
    hold: timedelta = timedelta(days=1),
    followed_plan: bool = True,
) -> ClosedTrade:
    """A closed trade; R defaults to pnl / 50 (1R = $50, as in the API tests)."""
    return ClosedTrade(
        trade_id=uuid.uuid7(),
        exit_at=_START + timedelta(days=day),
        pnl=Decimal(pnl),
        r_multiple=Decimal(r) if r is not None else Decimal(pnl) / 50,
        fees=Decimal(fees),
        hold_time=hold,
        followed_plan=followed_plan,
    )


def series(*pnls: str) -> list[ClosedTrade]:
    """One trade per day, in the order given."""
    return [trade(p, day=i) for i, p in enumerate(pnls)]


# --- outcome ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pnl", "expected"),
    [
        ("0.00000001", Outcome.WIN),
        ("-0.00000001", Outcome.LOSS),
        ("0", Outcome.BREAKEVEN),
        ("0E-8", Outcome.BREAKEVEN),
    ],
)
def test_outcome_is_the_sign_of_net_pnl(pnl: str, expected: Outcome) -> None:
    assert analytics.outcome(Decimal(pnl)) is expected


def test_a_gain_smaller_than_the_fees_is_a_loss() -> None:
    net = calculations.pnl(Side.LONG, Decimal(100), Decimal("100.50"), Decimal(1), Decimal(1))
    assert net == Decimal("-0.5")
    assert analytics.outcome(net) is Outcome.LOSS


# --- summarize: edge cases ----------------------------------------------------


def test_no_trades() -> None:
    s = analytics.summarize([])
    assert (s.trade_count, s.wins, s.losses, s.breakevens) == (0, 0, 0, 0)
    # Undefined, not zero: there is nothing to average.
    for undefined in (
        s.win_rate,
        s.expectancy,
        s.expectancy_r,
        s.average_win,
        s.average_loss,
        s.average_win_r,
        s.average_loss_r,
        s.largest_win,
        s.largest_loss,
        s.average_hold_time,
        s.average_hold_time_winners,
        s.average_hold_time_losers,
        s.plan_adherence_rate,
    ):
        assert undefined is None
    assert s.total_pnl == s.total_fees == s.max_drawdown == 0
    assert str(s.total_pnl) == "0E-8"  # quantized to 8 dp; the API prints 0.00000000


def test_all_wins() -> None:
    s = analytics.summarize(series("100", "50"))
    assert (s.wins, s.losses, s.breakevens) == (2, 0, 0)
    assert s.win_rate == Decimal("1.0000")
    assert s.expectancy == Decimal(75)
    assert s.expectancy_r == Decimal("1.5")
    assert s.largest_win == Decimal(100)
    assert s.average_loss is None
    assert s.largest_loss is None
    assert s.average_hold_time_losers is None
    assert s.max_drawdown == 0


def test_all_losses() -> None:
    s = analytics.summarize(series("-50", "-30"))
    assert s.win_rate == Decimal(0)  # a real 0%, not "no data"
    assert s.average_win is None
    assert s.largest_win is None
    assert s.largest_loss == Decimal(-50)
    assert s.average_loss == Decimal(-40)
    assert s.max_drawdown == Decimal(80)  # the peak starts at 0


def test_breakeven_only() -> None:
    s = analytics.summarize(series("0"))
    assert (s.wins, s.losses, s.breakevens) == (0, 0, 1)
    assert s.win_rate == Decimal(0)
    assert s.expectancy == Decimal(0)
    assert s.average_win is None
    assert s.average_loss is None
    assert s.average_hold_time == timedelta(days=1)
    assert s.average_hold_time_winners is None


def test_breakevens_count_in_the_win_rate_denominator() -> None:
    s = analytics.summarize(series("100", "-50", "0"))
    assert s.win_rate == Decimal("0.3333")  # 1 of 3, not 1 of 2
    assert s.expectancy == Decimal("16.66666667")
    assert s.expectancy_r == Decimal("0.3333")


def test_expectancy_matches_the_textbook_formula() -> None:
    trades = series("120", "-50", "0", "80", "-45", "0", "-60")
    s = analytics.summarize(trades)
    assert s.average_win is not None
    assert s.average_loss is not None
    # win rate x average win + loss rate x average loss, with exact fractions; breakevens add 0.
    formula = (s.wins * s.average_win + s.losses * s.average_loss) / s.trade_count
    assert formula.quantize(calculations.MONEY_QUANTUM) == s.expectancy


def test_totals_fees_and_plan_adherence() -> None:
    trades = [
        trade("100", fees="1.5", day=0),
        trade("-50", fees="2", day=1, followed_plan=False),
        trade("10", fees="0.25", day=2),
    ]
    s = analytics.summarize(trades)
    assert s.total_pnl == Decimal(60)
    assert s.total_fees == Decimal("3.75")
    assert s.plan_adherence_rate == Decimal("0.6667")  # 2 of 3, rounded half-even


def test_hold_time_averages_split_winners_and_losers() -> None:
    trades = [
        trade("100", hold=timedelta(days=4), day=0),
        trade("50", hold=timedelta(days=2), day=1),
        trade("-50", hold=timedelta(hours=6), day=2),
    ]
    s = analytics.summarize(trades)
    assert s.average_hold_time_winners == timedelta(days=3)
    assert s.average_hold_time_losers == timedelta(hours=6)
    assert s.average_hold_time == timedelta(days=2, hours=2)


def test_means_are_rounded_to_their_quantum() -> None:
    assert analytics.mean([Decimal(1), Decimal(1), Decimal(2)], calculations.MONEY_QUANTUM) == (
        Decimal("1.33333333")
    )
    assert analytics.mean([Decimal(1), Decimal(2)], calculations.R_QUANTUM) == Decimal("1.5000")
    assert analytics.ratio(1, 3) == Decimal("0.3333")
    assert analytics.ratio(0, 0) is None


# --- equity curve and drawdown --------------------------------------------------


def test_equity_curve_accumulates_in_close_order() -> None:
    first, second, third = series("100", "-30", "50")
    curve = analytics.equity_curve([third, first, second])  # input order doesn't matter
    assert [p.trade_id for p in curve] == [first.trade_id, second.trade_id, third.trade_id]
    assert [p.cumulative_pnl for p in curve] == [Decimal(100), Decimal(70), Decimal(120)]


def test_trades_closed_at_the_same_instant_are_ordered_by_id() -> None:
    a, b = trade("10"), trade("-10")  # same exit_at; uuid7 ids increase
    assert [p.trade_id for p in analytics.equity_curve([b, a])] == [a.trade_id, b.trade_id]


@pytest.mark.parametrize(
    ("pnls", "expected"),
    [
        ((), "0"),
        (("100", "50"), "0"),  # never fell
        (("-10", "30", "-5"), "10"),  # from the very first trade: the peak starts at 0
        (("100", "-30", "-20", "80", "-60"), "60"),  # 100 -> 50 is 50; 130 -> 70 is 60
        (("100", "-50", "200", "-40"), "50"),  # the new peak (250) resets the reference
        (("100", "-100", "-100"), "200"),  # below zero counts from the peak, not from 0
    ],
)
def test_max_drawdown(pnls: tuple[str, ...], expected: str) -> None:
    curve = analytics.equity_curve(series(*pnls))
    assert analytics.max_drawdown(curve) == Decimal(expected)


def test_summary_drawdown_matches_the_curve() -> None:
    trades = series("100", "-30", "-20", "80", "-60")
    assert analytics.summarize(trades).max_drawdown == analytics.max_drawdown(
        analytics.equity_curve(trades)
    )


# --- weekly counts ---------------------------------------------------------------

MON = date(2026, 10, 12)  # 2026-W42


def test_weekly_counts_fill_empty_weeks() -> None:
    days = [MON, MON + timedelta(days=4), MON + timedelta(weeks=2, days=6)]
    assert analytics.weekly_counts(days) == [
        WeekCount(MON, 2),
        WeekCount(MON + timedelta(weeks=1), 0),
        WeekCount(MON + timedelta(weeks=2), 1),
    ]


def test_weekly_counts_with_no_days() -> None:
    assert analytics.weekly_counts([]) == []
    assert analytics.weekly_counts([], first_week=MON + timedelta(days=3)) == [WeekCount(MON, 0)]


def test_weekly_counts_span_the_bounds_given() -> None:
    days = [MON + timedelta(weeks=1)]
    counts = analytics.weekly_counts(
        days, first_week=MON + timedelta(days=2), last_week=MON + timedelta(weeks=2)
    )
    assert counts == [
        WeekCount(MON, 0),
        WeekCount(MON + timedelta(weeks=1), 1),
        WeekCount(MON + timedelta(weeks=2), 0),
    ]
