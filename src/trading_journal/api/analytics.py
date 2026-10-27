"""Analytics over closed trades. Metric definitions: ADR 0011."""

from typing import Annotated

from fastapi import APIRouter, Query

from trading_journal.api.deps import AnalyticsServiceDep, CurrentUser
from trading_journal.domain.iso_week import week_label
from trading_journal.schemas.analytics import (
    AnalyticsParams,
    BreakdownGroupRead,
    BreakdownParams,
    EquityPointRead,
    SummaryRead,
    WeekCountRead,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

Params = Annotated[AnalyticsParams, Query()]


@router.get("/summary")
def summary(params: Params, user: CurrentUser, analytics: AnalyticsServiceDep) -> SummaryRead:
    """Performance of the closed trades that match the filters."""
    return SummaryRead.model_validate(analytics.summary(user.id, params))


@router.get("/equity-curve")
def equity_curve(
    params: Params, user: CurrentUser, analytics: AnalyticsServiceDep
) -> list[EquityPointRead]:
    """Cumulative net P/L after each closed trade, in close order."""
    return [EquityPointRead.model_validate(p) for p in analytics.equity_curve(user.id, params)]


@router.get("/breakdown")
def breakdown(
    params: Annotated[BreakdownParams, Query()], user: CurrentUser, analytics: AnalyticsServiceDep
) -> list[BreakdownGroupRead]:
    """The summary per strategy, symbol, side, asset type or exposure. Biggest groups first."""
    return [BreakdownGroupRead.model_validate(g) for g in analytics.breakdown(user.id, params)]


@router.get("/frequency")
def frequency(
    params: Params, user: CurrentUser, analytics: AnalyticsServiceDep
) -> list[WeekCountRead]:
    """Trades opened per ISO week (UTC), with empty weeks as 0. Dates filter on entry."""
    return [
        WeekCountRead(week=week_label(w.week_start), week_start=w.week_start, trades_opened=w.count)
        for w in analytics.frequency(user.id, params)
    ]
