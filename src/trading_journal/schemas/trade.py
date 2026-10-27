"""Trade request and response models.

Shape rules (types, ranges, formats) live here. Business rules (stop side, leverage only
on ETFs, transitions) live in the service, so create and PATCH share them.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from trading_journal.domain import calculations
from trading_journal.domain.enums import AssetType, Exposure, Side, TradeSource, TradeStatus
from trading_journal.schemas.base import RequestModel


def _normalize_symbol(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


# Normalized *before* the pattern check, so "brk.b" is accepted and stored as "BRK.B".
# (StringConstraints' own to_upper runs after its pattern check, which rejects it.)
Symbol = Annotated[
    str,
    BeforeValidator(_normalize_symbol),
    StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9.\-/]{0,31}$"),
]
# NUMERIC(20, 8): 12 integer digits and 8 decimals.
Price = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8)]
Fees = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=8)]
Leverage = Literal[2, 3, -2, -3]
Thesis = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]
ExternalId = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TradeCreate(RequestModel):
    """A new trade is always a plan. Entry and exit come later, through /open and /close."""

    strategy_id: uuid.UUID | None = None
    symbol: Symbol
    asset_type: AssetType
    leverage_factor: Leverage | None = None
    side: Side
    planned_entry: Price
    planned_stop: Price
    planned_target: Price
    thesis: Thesis
    source: TradeSource = TradeSource.MANUAL
    external_id: ExternalId | None = None


# Fields of the plan; they can only change while the trade is planned (ADR 0008).
PLAN_FIELDS = frozenset(
    {
        "symbol",
        "asset_type",
        "leverage_factor",
        "side",
        "planned_entry",
        "planned_stop",
        "planned_target",
        "thesis",
    }
)
_NULLABLE = frozenset({"strategy_id", "leverage_factor"})


class TradeUpdate(RequestModel):
    """PATCH: only the fields sent are changed. Sending null clears a nullable field."""

    strategy_id: uuid.UUID | None = None
    symbol: Symbol | None = None
    asset_type: AssetType | None = None
    leverage_factor: Leverage | None = None
    side: Side | None = None
    planned_entry: Price | None = None
    planned_stop: Price | None = None
    planned_target: Price | None = None
    thesis: Thesis | None = None

    @model_validator(mode="after")
    def required_fields_not_null(self) -> TradeUpdate:
        nulled = sorted(
            name for name in self.model_fields_set - _NULLABLE if getattr(self, name) is None
        )
        if nulled:
            raise ValueError(f"cannot be null: {', '.join(nulled)}")
        return self


class TradeOpen(RequestModel):
    entry_price: Price
    quantity: Quantity
    entry_at: AwareDatetime | None = None  # defaults to now


class TradeClose(RequestModel):
    exit_price: Price
    exit_at: AwareDatetime | None = None  # defaults to now
    fees: Fees = Decimal(0)
    followed_plan: bool


class TradeListParams(BaseModel):
    """Query parameters for GET /trades: equality filters plus keyset pagination."""

    status: TradeStatus | None = None
    strategy_id: uuid.UUID | None = None
    symbol: Symbol | None = None
    side: Side | None = None
    asset_type: AssetType | None = None
    source: TradeSource | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: uuid.UUID | None = None


class TradeRead(BaseModel):
    """A trade plus its derived values, which are computed here and never accepted as input."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID | None
    symbol: str
    asset_type: AssetType
    leverage_factor: int | None
    side: Side
    status: TradeStatus
    planned_entry: Decimal
    planned_stop: Decimal
    planned_target: Decimal
    thesis: str
    entry_price: Decimal | None
    entry_at: datetime | None
    quantity: Decimal | None
    exit_price: Decimal | None
    exit_at: datetime | None
    fees: Decimal | None
    followed_plan: bool | None
    source: TradeSource
    external_id: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def exposure(self) -> Exposure:
        return calculations.exposure(self.side, self.leverage_factor)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def r_per_share(self) -> Decimal:
        return calculations.r_per_share(self.planned_entry, self.planned_stop)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pnl(self) -> Decimal | None:
        """Net P/L in dollars, after fees. Null until the trade is closed."""
        if (
            self.entry_price is None
            or self.exit_price is None
            or self.quantity is None
            or self.fees is None
        ):
            return None
        return calculations.pnl(
            self.side, self.entry_price, self.exit_price, self.quantity, self.fees
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def r_multiple(self) -> Decimal | None:
        net = self.pnl
        if net is None or self.quantity is None:
            return None
        return calculations.r_multiple(net, self.quantity, self.r_per_share)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hold_time(self) -> timedelta | None:
        if self.entry_at is None or self.exit_at is None:
            return None
        return calculations.hold_time(self.entry_at, self.exit_at)
