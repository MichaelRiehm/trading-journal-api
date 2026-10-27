"""Business rules for a trade's plan. The CHECK constraints are the backstop (ADR 0004)."""

from decimal import Decimal

from trading_journal.domain.enums import AssetType, Side
from trading_journal.domain.errors import InvalidInputError


def check_plan(
    *,
    side: Side,
    planned_entry: Decimal,
    planned_stop: Decimal,
    asset_type: AssetType,
    leverage_factor: int | None,
) -> None:
    """Raise InvalidInputError (422) if the plan breaks a rule."""
    if side is Side.LONG and not planned_stop < planned_entry:
        raise InvalidInputError("For a long trade, planned_stop must be below planned_entry")
    if side is Side.SHORT and not planned_stop > planned_entry:
        raise InvalidInputError("For a short trade, planned_stop must be above planned_entry")
    if leverage_factor is not None and asset_type is not AssetType.ETF:
        # Leveraged and inverse products are ETFs. See ADR 0007.
        raise InvalidInputError("leverage_factor is only allowed for ETFs")
