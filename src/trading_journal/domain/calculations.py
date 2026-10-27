"""Trade math: pure functions on Decimals, shared by the trade responses and analytics.

See ADR 0008 for the definitions. No floats anywhere.
"""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from trading_journal.domain.enums import Exposure, Side

MONEY_QUANTUM = Decimal("0.00000001")  # matches NUMERIC(20, 8)
R_QUANTUM = Decimal("0.0001")

# NUMERIC(20, 8) x NUMERIC(20, 8) can need ~40 significant digits before rounding;
# the default context keeps 28.
_PRECISION = 50


def pnl(
    side: Side, entry_price: Decimal, exit_price: Decimal, quantity: Decimal, fees: Decimal
) -> Decimal:
    """Net profit or loss in dollars: the price move times quantity, minus fees."""
    with localcontext(prec=_PRECISION):
        move = exit_price - entry_price if side is Side.LONG else entry_price - exit_price
        return (move * quantity - fees).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def r_per_share(planned_entry: Decimal, planned_stop: Decimal) -> Decimal:
    """The planned risk per share: the distance from the planned entry to the stop."""
    risk = abs(planned_entry - planned_stop)
    if risk == 0:
        # The stop_on_losing_side constraint makes this unreachable for stored trades.
        raise ValueError("planned_stop must differ from planned_entry")
    return risk


def r_multiple(net_pnl: Decimal, quantity: Decimal, risk_per_share: Decimal) -> Decimal:
    """Net P/L per share in units of planned risk. +2R made twice the risk, -1R lost it."""
    with localcontext(prec=_PRECISION):
        return (net_pnl / quantity / risk_per_share).quantize(R_QUANTUM, rounding=ROUND_HALF_EVEN)


def hold_time(entry_at: datetime, exit_at: datetime) -> timedelta:
    return exit_at - entry_at


def exposure(side: Side, leverage_factor: int | None) -> Exposure:
    """Bearish for a short, or for a long in an inverse ETF (negative leverage). ADR 0007."""
    inverse = leverage_factor is not None and leverage_factor < 0
    bearish = (side is Side.SHORT) != inverse
    return Exposure.BEARISH if bearish else Exposure.BULLISH
