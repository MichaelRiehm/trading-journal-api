"""Which journal phases a trade can take, given its status. See ADR 0010.

A phase may not run ahead of the trade (no "post" reflection on a trade that hasn't
finished), but writing about the past is allowed, so a "pre" note can be backfilled on a
closed trade.
"""

from trading_journal.domain.enums import JournalPhase, TradeStatus
from trading_journal.domain.errors import ConflictError

_PRE, _DURING, _POST = JournalPhase.PRE, JournalPhase.DURING, JournalPhase.POST

ALLOWED_PHASES: dict[TradeStatus, frozenset[JournalPhase]] = {
    TradeStatus.PLANNED: frozenset({_PRE}),
    TradeStatus.OPEN: frozenset({_PRE, _DURING}),
    TradeStatus.CLOSED: frozenset({_PRE, _DURING, _POST}),
    # A cancelled trade never opened, so there is nothing to write "during".
    TradeStatus.CANCELLED: frozenset({_PRE, _POST}),
}

# The phase used when a new entry doesn't say: whatever the trade is in right now.
DEFAULT_PHASE: dict[TradeStatus, JournalPhase] = {
    TradeStatus.PLANNED: _PRE,
    TradeStatus.OPEN: _DURING,
    TradeStatus.CLOSED: _POST,
    TradeStatus.CANCELLED: _POST,
}

_NEEDS = {
    _PRE: "any trade",
    _DURING: "a trade that was opened",
    _POST: "a closed or cancelled trade",
}


def ensure_phase_allowed(status: TradeStatus, phase: JournalPhase) -> None:
    """Raise ConflictError (409) if a `phase` entry can't be written for a `status` trade."""
    if phase not in ALLOWED_PHASES[status]:
        raise ConflictError(f"A {phase} entry needs {_NEEDS[phase]}; this one is {status}")
