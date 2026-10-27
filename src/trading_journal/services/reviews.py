"""The weekly review (ADR 0012): what closed and what was cancelled in one ISO week."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from trading_journal.domain import analytics, iso_week
from trading_journal.models import JournalEntry, Trade
from trading_journal.repositories import JournalEntryRepository, TradeRepository
from trading_journal.services.analytics import closed_trade


@dataclass(frozen=True, slots=True)
class WeeklyReview:
    monday: date
    starts_at: datetime
    ends_at: datetime
    summary: analytics.Summary
    closed: Sequence[Trade]
    cancelled: Sequence[Trade]
    entries: dict[uuid.UUID, list[JournalEntry]]  # by trade id, oldest first


class ReviewService:
    def __init__(self, session: Session) -> None:
        self._trades = TradeRepository(session)
        self._journal = JournalEntryRepository(session)

    def weekly(self, user_id: uuid.UUID, week: str | None) -> WeeklyReview:
        monday = (
            iso_week.parse_iso_week(week) if week else iso_week.week_start(datetime.now(UTC).date())
        )
        starts_at, ends_at = iso_week.week_bounds(monday)
        closed = self._trades.list_closed(user_id, exited_from=starts_at, exited_before=ends_at)
        cancelled = self._trades.list_cancelled(
            user_id, cancelled_from=starts_at, cancelled_before=ends_at
        )

        # One query for every trade's journal, not one per trade.
        entries: defaultdict[uuid.UUID, list[JournalEntry]] = defaultdict(list)
        for entry in self._journal.list_for_trades(user_id, [t.id for t in (*closed, *cancelled)]):
            entries[entry.trade_id].append(entry)

        return WeeklyReview(
            monday=monday,
            starts_at=starts_at,
            ends_at=ends_at,
            summary=analytics.summarize(closed_trade(t) for t in closed),
            closed=closed,
            cancelled=cancelled,
            entries=dict(entries),
        )
