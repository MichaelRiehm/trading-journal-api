"""Journal entries.

Created and listed under their trade (`/trades/{id}/journal`); edited and deleted by their
own id (`/journal/{entry_id}`), so a client doesn't need the trade id to fix a typo.
"""

import uuid

from fastapi import APIRouter, status

from trading_journal.api.deps import CurrentUser, JournalServiceDep
from trading_journal.api.errors import Responses
from trading_journal.domain.enums import JournalPhase
from trading_journal.schemas.journal import (
    JournalEntryCreate,
    JournalEntryRead,
    JournalEntryUpdate,
)

trade_journal_router = APIRouter(prefix="/trades/{trade_id}/journal", tags=["journal"])
entry_router = APIRouter(prefix="/journal", tags=["journal"])

_TRADE_NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Trade not found"}}
_ENTRY_NOT_FOUND: Responses = {
    status.HTTP_404_NOT_FOUND: {"description": "Journal entry not found"}
}
_PHASE_CONFLICT: Responses = {
    status.HTTP_409_CONFLICT: {"description": "The phase runs ahead of the trade's status"}
}


@trade_journal_router.post(
    "", status_code=status.HTTP_201_CREATED, responses=_TRADE_NOT_FOUND | _PHASE_CONFLICT
)
def create_entry(
    trade_id: uuid.UUID, body: JournalEntryCreate, user: CurrentUser, journal: JournalServiceDep
) -> JournalEntryRead:
    """Add an entry. `phase` defaults to where the trade is now; it can't run ahead of it."""
    return JournalEntryRead.model_validate(journal.create(user.id, trade_id, body))


@trade_journal_router.get("", responses=_TRADE_NOT_FOUND)
def list_entries(
    trade_id: uuid.UUID,
    user: CurrentUser,
    journal: JournalServiceDep,
    phase: JournalPhase | None = None,
) -> list[JournalEntryRead]:
    """Oldest first."""
    return [JournalEntryRead.model_validate(e) for e in journal.list(user.id, trade_id, phase)]


@entry_router.patch("/{entry_id}", responses=_ENTRY_NOT_FOUND | _PHASE_CONFLICT)
def update_entry(
    entry_id: uuid.UUID, body: JournalEntryUpdate, user: CurrentUser, journal: JournalServiceDep
) -> JournalEntryRead:
    return JournalEntryRead.model_validate(journal.update(user.id, entry_id, body))


@entry_router.delete(
    "/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ENTRY_NOT_FOUND
)
def delete_entry(entry_id: uuid.UUID, user: CurrentUser, journal: JournalServiceDep) -> None:
    journal.delete(user.id, entry_id)
