"""Analytics query parameters and responses. Definitions of each metric: ADR 0011."""

import uuid
from datetime import date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from trading_journal.domain.enums import AssetType, Side, TradeSource
from trading_journal.schemas.base import DecimalOut
from trading_journal.schemas.trade import Symbol


class AnalyticsParams(BaseModel):
    """Filters shared by the analytics endpoints. Dates are inclusive and in UTC.

    The date range applies to when trades closed, except for /frequency, which counts
    trades by when they were opened.
    """

    start_date: date | None = None
    end_date: date | None = None
    strategy_id: uuid.UUID | None = None
    symbol: Symbol | None = None
    side: Side | None = None
    asset_type: AssetType | None = None
    source: TradeSource | None = None

    @model_validator(mode="after")
    def end_not_before_start(self) -> AnalyticsParams:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class BreakdownBy(StrEnum):
    STRATEGY = "strategy"
    SYMBOL = "symbol"
    SIDE = "side"
    ASSET_TYPE = "asset_type"
    EXPOSURE = "exposure"  # bullish/bearish, so inverse-ETF longs group with shorts


class BreakdownParams(AnalyticsParams):
    by: BreakdownBy


class SummaryRead(BaseModel):
    """Rates are fractions (0.5 is 50%). Losses are negative. Null means "no trades to
    average", which is different from 0."""

    model_config = ConfigDict(from_attributes=True)

    trade_count: int
    wins: int
    losses: int
    breakevens: int
    win_rate: DecimalOut | None
    expectancy: DecimalOut | None
    expectancy_r: DecimalOut | None
    average_win: DecimalOut | None
    average_loss: DecimalOut | None
    average_win_r: DecimalOut | None
    average_loss_r: DecimalOut | None
    total_pnl: DecimalOut
    total_fees: DecimalOut
    largest_win: DecimalOut | None
    largest_loss: DecimalOut | None
    average_hold_time: timedelta | None
    average_hold_time_winners: timedelta | None
    average_hold_time_losers: timedelta | None
    plan_adherence_rate: DecimalOut | None
    max_drawdown: DecimalOut


class EquityPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_id: uuid.UUID
    exit_at: datetime
    pnl: DecimalOut
    cumulative_pnl: DecimalOut


class BreakdownGroupRead(BaseModel):
    """`key` is the raw value (a strategy id, a symbol...), null for trades without a
    strategy; `label` is for display."""

    model_config = ConfigDict(from_attributes=True)

    key: str | None
    label: str
    summary: SummaryRead


class WeekCountRead(BaseModel):
    week: str  # "2026-W42"
    week_start: date
    trades_opened: int
