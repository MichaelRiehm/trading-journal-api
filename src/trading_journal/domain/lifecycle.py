"""The trade lifecycle: planned -> open -> closed, planned -> cancelled. See ADR 0008."""

from trading_journal.domain.enums import TradeStatus
from trading_journal.domain.errors import ConflictError

ALLOWED_TRANSITIONS: dict[TradeStatus, frozenset[TradeStatus]] = {
    TradeStatus.PLANNED: frozenset({TradeStatus.OPEN, TradeStatus.CANCELLED}),
    TradeStatus.OPEN: frozenset({TradeStatus.CLOSED}),
    TradeStatus.CLOSED: frozenset(),
    TradeStatus.CANCELLED: frozenset(),
}

_VERB = {
    TradeStatus.OPEN: "open",
    TradeStatus.CLOSED: "close",
    TradeStatus.CANCELLED: "cancel",
}


def ensure_can_transition(current: TradeStatus, target: TradeStatus) -> None:
    """Raise ConflictError (409) unless current -> target is a legal move."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ConflictError(f"Cannot {_VERB.get(target, target.value)} a trade that is {current}")


def plan_is_editable(status: TradeStatus) -> bool:
    # Once entered, the plan is the record that plan adherence is measured against.
    return status is TradeStatus.PLANNED
