"""Unit tests for the phase rules. No database."""

import pytest

from trading_journal.domain import journal_rules
from trading_journal.domain.enums import JournalPhase, TradeStatus
from trading_journal.domain.errors import ConflictError
from trading_journal.domain.lifecycle import ALLOWED_TRANSITIONS


def test_every_status_has_rules() -> None:
    assert set(journal_rules.ALLOWED_PHASES) == set(TradeStatus)
    assert set(journal_rules.DEFAULT_PHASE) == set(TradeStatus)


@pytest.mark.parametrize("status", list(TradeStatus))
def test_default_phase_is_allowed(status: TradeStatus) -> None:
    assert journal_rules.DEFAULT_PHASE[status] in journal_rules.ALLOWED_PHASES[status]


@pytest.mark.parametrize(
    ("current", "target"),
    [(c, t) for c, targets in ALLOWED_TRANSITIONS.items() for t in targets],
    ids=lambda s: str(s),
)
def test_allowed_phases_only_grow_along_transitions(
    current: TradeStatus, target: TradeStatus
) -> None:
    # This is why journal writes need no row lock: if an entry was valid when written, a
    # concurrent transition can only move the trade to a status where it is still valid.
    assert journal_rules.ALLOWED_PHASES[current] <= journal_rules.ALLOWED_PHASES[target]


def test_pre_is_always_allowed_for_backfilling() -> None:
    for status in TradeStatus:
        journal_rules.ensure_phase_allowed(status, JournalPhase.PRE)


def test_message_says_what_is_needed() -> None:
    with pytest.raises(ConflictError) as excinfo:
        journal_rules.ensure_phase_allowed(TradeStatus.OPEN, JournalPhase.POST)

    assert (
        excinfo.value.message == "A post entry needs a closed or cancelled trade; this one is open"
    )
