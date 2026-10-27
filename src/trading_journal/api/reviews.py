"""The weekly review: the reflection feature (ADR 0012)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query

from trading_journal.api.deps import CurrentUser, ReviewServiceDep
from trading_journal.domain.enums import JournalPhase
from trading_journal.domain.iso_week import week_label
from trading_journal.models import JournalEntry, Trade
from trading_journal.schemas.analytics import SummaryRead
from trading_journal.schemas.journal import JournalEntryRead
from trading_journal.schemas.review import (
    PhaseEntries,
    ReviewTrade,
    WeeklyReviewParams,
    WeeklyReviewRead,
)
from trading_journal.schemas.trade import TradeRead

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/weekly")
def weekly_review(
    params: Annotated[WeeklyReviewParams, Query()], user: CurrentUser, reviews: ReviewServiceDep
) -> WeeklyReviewRead:
    """Trades closed and cancelled in an ISO week (`2026-W42`, UTC), the week's summary,
    and every journal entry for those trades, grouped by phase."""
    review = reviews.weekly(user.id, params.week)

    def with_journal(trades: Sequence[Trade]) -> list[ReviewTrade]:
        return [
            ReviewTrade(
                trade=TradeRead.model_validate(t), journal=_by_phase(review.entries.get(t.id, []))
            )
            for t in trades
        ]

    return WeeklyReviewRead(
        week=week_label(review.monday),
        starts_at=review.starts_at,
        ends_at=review.ends_at,
        summary=SummaryRead.model_validate(review.summary),
        closed=with_journal(review.closed),
        cancelled=with_journal(review.cancelled),
    )


def _by_phase(entries: Sequence[JournalEntry]) -> PhaseEntries:
    def of(phase: JournalPhase) -> list[JournalEntryRead]:
        return [JournalEntryRead.model_validate(e) for e in entries if e.phase == phase]

    return PhaseEntries(
        pre=of(JournalPhase.PRE), during=of(JournalPhase.DURING), post=of(JournalPhase.POST)
    )
