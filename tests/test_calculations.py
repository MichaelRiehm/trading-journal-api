"""Unit tests for the trade math. Pure functions: no database, no HTTP."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from trading_journal.domain import calculations
from trading_journal.domain.enums import Exposure, Side

D = Decimal


@pytest.mark.parametrize(
    ("side", "entry", "exit_", "qty", "fees", "expected"),
    [
        pytest.param(Side.LONG, "100", "110", "10", "0", "100", id="long-winner"),
        pytest.param(Side.LONG, "100", "95", "10", "0", "-50", id="long-loser"),
        pytest.param(Side.SHORT, "100", "90", "10", "0", "100", id="short-winner"),
        pytest.param(Side.SHORT, "100", "105", "10", "0", "-50", id="short-loser"),
        pytest.param(Side.LONG, "100", "110", "10", "2.50", "97.50", id="fees-reduce-a-win"),
        pytest.param(Side.SHORT, "100", "105", "10", "1", "-51", id="fees-deepen-a-loss"),
        pytest.param(Side.LONG, "100", "100", "10", "1", "-1", id="scratch-costs-fees"),
        pytest.param(
            Side.LONG, "0.00001234", "0.00002468", "1000000", "0", "12.34", id="sub-cent-crypto"
        ),
        pytest.param(Side.LONG, "64000", "65000", "0.015", "0", "15", id="fractional-crypto"),
    ],
)
def test_pnl(side: Side, entry: str, exit_: str, qty: str, fees: str, expected: str) -> None:
    result = calculations.pnl(side, D(entry), D(exit_), D(qty), D(fees))

    assert result == D(expected)
    assert result.as_tuple().exponent == -8  # always quantized to NUMERIC(20, 8)


def test_pnl_is_exact_where_float_is_not() -> None:
    # 0.1 + 0.2 != 0.3 in float. In Decimal it is exact.
    assert calculations.pnl(Side.LONG, D("0.1"), D("0.4"), D("1"), D("0.0")) == D("0.3")


def test_pnl_rounds_half_even_at_the_eighth_decimal() -> None:
    # 0.00000001 x 0.5 = 0.000000005, exactly halfway: half-even rounds to the even digit (0).
    assert calculations.pnl(Side.LONG, D("1"), D("1.00000001"), D("0.5"), D("0")) == D("0.00000000")
    # 0.00000003 x 0.5 = 0.000000015: rounds to 0.00000002 (even).
    assert calculations.pnl(Side.LONG, D("1"), D("1.00000003"), D("0.5"), D("0")) == D("0.00000002")


@pytest.mark.parametrize(
    ("entry", "stop", "expected"),
    [("100", "95", "5"), ("100", "105", "5"), ("0.5", "0.45", "0.05")],
)
def test_r_per_share(entry: str, stop: str, expected: str) -> None:
    assert calculations.r_per_share(D(entry), D(stop)) == D(expected)


def test_r_per_share_rejects_zero_risk() -> None:
    with pytest.raises(ValueError, match="planned_stop"):
        calculations.r_per_share(D("100"), D("100"))


@pytest.mark.parametrize(
    ("net_pnl", "qty", "risk", "expected"),
    [
        pytest.param("100", "10", "5", "2.0000", id="2R-winner"),
        pytest.param("-50", "10", "5", "-1.0000", id="stopped-out-1R"),
        pytest.param("-1", "10", "5", "-0.0200", id="scratch-after-fees"),
        pytest.param("100", "3", "7", "4.7619", id="rounded-to-4-places"),
    ],
)
def test_r_multiple(net_pnl: str, qty: str, risk: str, expected: str) -> None:
    assert calculations.r_multiple(D(net_pnl), D(qty), D(risk)) == D(expected)


def test_r_multiple_uses_actual_entry_and_counts_fees() -> None:
    # Planned entry 100, stop 95 (R = 5). Actually entered at 101, exited at 111, fees 10.
    net = calculations.pnl(Side.LONG, D("101"), D("111"), D("10"), D("10"))
    r = calculations.r_per_share(D("100"), D("95"))

    # (100 - 10) / 10 shares = 9 per share = 1.8R. Gross, it would have been 2R.
    assert calculations.r_multiple(net, D("10"), r) == D("1.8")


def test_hold_time() -> None:
    entry = datetime(2026, 10, 1, 14, 30, tzinfo=UTC)
    exit_ = datetime(2026, 10, 3, 19, 0, tzinfo=UTC)

    assert calculations.hold_time(entry, exit_) == timedelta(days=2, hours=4, minutes=30)


@pytest.mark.parametrize(
    ("side", "leverage", "expected"),
    [
        (Side.LONG, None, Exposure.BULLISH),
        (Side.LONG, 3, Exposure.BULLISH),  # TQQQ
        (Side.LONG, -3, Exposure.BEARISH),  # SQQQ: long an inverse ETF
        (Side.SHORT, None, Exposure.BEARISH),
        (Side.SHORT, 2, Exposure.BEARISH),
        (Side.SHORT, -2, Exposure.BULLISH),  # short an inverse ETF
    ],
)
def test_exposure(side: Side, leverage: int | None, expected: Exposure) -> None:
    assert calculations.exposure(side, leverage) is expected
