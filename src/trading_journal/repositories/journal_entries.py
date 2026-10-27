import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from trading_journal.domain.enums import JournalPhase
from trading_journal.models import JournalEntry, Trade


class JournalEntryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, trade_id: uuid.UUID, phase: JournalPhase, body: str) -> JournalEntry:
        # The caller must already have loaded the trade through TradeRepository.get,
        # which is where ownership is checked.
        entry = JournalEntry(trade_id=trade_id, phase=phase, body=body)
        self._session.add(entry)
        self._session.flush()
        return entry

    def get(self, user_id: uuid.UUID, entry_id: uuid.UUID) -> JournalEntry | None:
        # Ownership follows the trade.
        return self._session.scalar(
            select(JournalEntry)
            .join(Trade, JournalEntry.trade_id == Trade.id)
            .where(JournalEntry.id == entry_id, Trade.user_id == user_id)
        )

    def list_for_trade(
        self, user_id: uuid.UUID, trade_id: uuid.UUID, phase: JournalPhase | None = None
    ) -> Sequence[JournalEntry]:
        """Oldest first. The UUIDv7 id breaks ties between entries with the same created_at."""
        query = (
            select(JournalEntry)
            .join(Trade, JournalEntry.trade_id == Trade.id)
            .where(JournalEntry.trade_id == trade_id, Trade.user_id == user_id)
        )
        if phase is not None:
            query = query.where(JournalEntry.phase == phase)
        return self._session.scalars(query.order_by(JournalEntry.created_at, JournalEntry.id)).all()

    def save(self, entry: JournalEntry) -> JournalEntry:
        self._session.flush()
        return entry

    def delete(self, entry: JournalEntry) -> None:
        self._session.delete(entry)
        self._session.flush()
