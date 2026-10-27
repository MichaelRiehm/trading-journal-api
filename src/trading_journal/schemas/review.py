"""The weekly review: the week's closed and cancelled trades with their journals (ADR 0012)."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel

from trading_journal.domain.iso_week import parse_iso_week
from trading_journal.schemas.analytics import SummaryRead
from trading_journal.schemas.journal import JournalEntryRead
from trading_journal.schemas.trade import TradeRead


def _check_week(value: str) -> str:
    parse_iso_week(value)  # a ValueError here becomes a 422
    return value


IsoWeek = Annotated[str, AfterValidator(_check_week)]


class WeeklyReviewParams(BaseModel):
    week: IsoWeek | None = None  # "2026-W42"; defaults to the current week (UTC)


class PhaseEntries(BaseModel):
    """Journal entries split by phase, each list oldest first."""

    pre: list[JournalEntryRead]
    during: list[JournalEntryRead]
    post: list[JournalEntryRead]


class ReviewTrade(BaseModel):
    trade: TradeRead
    journal: PhaseEntries


class WeeklyReviewRead(BaseModel):
    week: str
    starts_at: datetime  # Monday 00:00 UTC
    ends_at: datetime  # the next Monday, excluded
    summary: SummaryRead  # the week's closed trades only
    closed: list[ReviewTrade]
    cancelled: list[ReviewTrade]
