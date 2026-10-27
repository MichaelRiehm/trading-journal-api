"""The database rejects illegal data even if a service-layer check is missed."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from factories import add_trade, make_user
from trading_journal.domain.enums import AssetType, Side, TradeStatus
from trading_journal.repositories import StrategyRepository, UserRepository

OPENED: dict[str, Any] = {
    "status": TradeStatus.OPEN,
    "entry_price": Decimal("100"),
    "entry_at": datetime(2026, 10, 1, tzinfo=UTC),
    "quantity": Decimal("5"),
}


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"planned_entry": Decimal("-1"), "planned_stop": Decimal("-2")}, "prices_positive"),
        ({"planned_stop": Decimal("105")}, "stop_on_losing_side"),  # long, stop above entry
        ({"side": Side.SHORT, "planned_stop": Decimal("95")}, "stop_on_losing_side"),
        ({"asset_type": AssetType.ETF, "leverage_factor": 4}, "leverage_factor_allowed"),
        ({"leverage_factor": 2}, "leverage_only_etf"),  # the factory's default is a stock
        ({"symbol": "aapl"}, "symbol_uppercase"),
        ({**OPENED, "quantity": Decimal("0")}, "quantity_positive"),
        ({"status": TradeStatus.OPEN}, "status_fields"),  # open without entry fields
        ({"entry_price": Decimal("100")}, "status_fields"),  # planned with an entry
        ({"status": TradeStatus.CANCELLED}, "status_fields"),  # cancelled without cancelled_at
        ({"cancelled_at": datetime(2026, 10, 2, tzinfo=UTC)}, "status_fields"),  # planned with it
        ({**OPENED, "cancelled_at": datetime(2026, 10, 2, tzinfo=UTC)}, "status_fields"),
        (
            {
                **OPENED,
                "status": TradeStatus.CLOSED,
                "exit_price": Decimal("90"),
                "exit_at": datetime(2026, 10, 2, tzinfo=UTC),
                "fees": Decimal("-1"),
                "followed_plan": False,
            },
            "fees_non_negative",
        ),
        (
            {
                **OPENED,
                "status": TradeStatus.CLOSED,
                "exit_price": Decimal("90"),
                "exit_at": datetime(2026, 9, 1, tzinfo=UTC),  # before entry
                "fees": Decimal("0"),
                "followed_plan": False,
            },
            "exit_after_entry",
        ),
    ],
)
def test_illegal_trades_are_rejected(
    session: Session, overrides: dict[str, Any], constraint: str
) -> None:
    user = make_user(session)
    with pytest.raises(IntegrityError, match=f"ck_trades_{constraint}"):
        add_trade(session, user.id, **overrides)


def test_valid_short_and_inverse_etf_trades_are_accepted(session: Session) -> None:
    user = make_user(session)
    add_trade(session, user.id, side=Side.SHORT, planned_stop=Decimal("105"))
    # An inverse ETF is a LONG trade with a negative leverage factor.
    add_trade(session, user.id, symbol="SQQQ", asset_type=AssetType.ETF, leverage_factor=-3)


def test_trade_cannot_use_another_users_strategy(session: Session) -> None:
    alice, bob = make_user(session), make_user(session)
    bobs_strategy = StrategyRepository(session).add(user_id=bob.id, name="Bob's setup")

    with pytest.raises(IntegrityError, match="fk_trades_strategy_id_user_id_strategies"):
        add_trade(session, alice.id, strategy_id=bobs_strategy.id)


def test_strategy_with_trades_cannot_be_deleted(session: Session) -> None:
    user = make_user(session)
    strategies = StrategyRepository(session)
    strategy = strategies.add(user_id=user.id, name="Momentum")
    add_trade(session, user.id, strategy_id=strategy.id)

    with pytest.raises(IntegrityError, match="fk_trades_strategy_id_user_id_strategies"):
        strategies.delete(strategy)


def test_emails_must_be_stored_lowercase(session: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        UserRepository(session).add(email="Trader@Example.com", password_hash="x")


def test_unknown_enum_value_is_rejected_by_the_database(session: Session) -> None:
    user = make_user(session)
    trade = add_trade(session, user.id)

    # Raw SQL bypasses the ORM's own enum validation, proving the CHECK constraint exists.
    with pytest.raises(IntegrityError, match="ck_trades_side"):
        session.execute(text("UPDATE trades SET side = 'flat' WHERE id = :id"), {"id": trade.id})
