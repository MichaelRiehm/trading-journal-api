import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from trading_journal.domain import journal_rules
from trading_journal.domain.enums import JournalPhase
from trading_journal.domain.errors import NotFoundError
from trading_journal.models import JournalEntry, Trade
from trading_journal.repositories import JournalEntryRepository, TradeRepository
from trading_journal.schemas.journal import JournalEntryCreate, JournalEntryUpdate


class JournalService:
    """Journal entries. Ownership follows the trade: every lookup goes through the trade's
    user_id, so another user's trade or entry is simply not found.

    No row lock is needed (unlike trade transitions): statuses only move forward and each
    status allows a superset of the previous one's phases, so a concurrent transition can
    never make an accepted entry invalid. See ADR 0010.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entries = JournalEntryRepository(session)
        self._trades = TradeRepository(session)

    def create(
        self, user_id: uuid.UUID, trade_id: uuid.UUID, data: JournalEntryCreate
    ) -> JournalEntry:
        trade = self._trade(user_id, trade_id)
        phase = data.phase or journal_rules.DEFAULT_PHASE[trade.status]
        journal_rules.ensure_phase_allowed(trade.status, phase)
        entry = self._entries.add(trade_id=trade.id, phase=phase, body=data.body)
        self._session.commit()
        return entry

    def list(
        self, user_id: uuid.UUID, trade_id: uuid.UUID, phase: JournalPhase | None = None
    ) -> Sequence[JournalEntry]:
        self._trade(user_id, trade_id)  # 404 for a missing or foreign trade, not an empty list
        return self._entries.list_for_trade(user_id, trade_id, phase)

    def update(
        self, user_id: uuid.UUID, entry_id: uuid.UUID, data: JournalEntryUpdate
    ) -> JournalEntry:
        entry = self._entry(user_id, entry_id)
        if data.phase is not None and data.phase != entry.phase:
            trade = self._trade(user_id, entry.trade_id)
            journal_rules.ensure_phase_allowed(trade.status, data.phase)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(entry, field, value)
        self._entries.save(entry)
        self._session.commit()
        return entry

    def delete(self, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
        self._entries.delete(self._entry(user_id, entry_id))
        self._session.commit()

    def _trade(self, user_id: uuid.UUID, trade_id: uuid.UUID) -> Trade:
        trade = self._trades.get(user_id, trade_id)
        if trade is None:
            raise NotFoundError("Trade")
        return trade

    def _entry(self, user_id: uuid.UUID, entry_id: uuid.UUID) -> JournalEntry:
        entry = self._entries.get(user_id, entry_id)
        if entry is None:
            raise NotFoundError("Journal entry")
        return entry
