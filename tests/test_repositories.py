"""Repository behaviour against a real Postgres, including ownership scoping."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from factories import add_trade, make_user
from trading_journal.domain.enums import AssetType, JournalPhase, TradeSource, TradeStatus
from trading_journal.repositories import (
    JournalEntryRepository,
    StrategyRepository,
    TradeRepository,
    UserRepository,
)


def test_user_round_trip(session: Session) -> None:
    user = make_user(session, email="trader@example.com")

    assert isinstance(user.id, uuid.UUID)
    assert user.id.version == 7
    assert user.created_at.tzinfo is not None  # timestamptz, loaded via eager_defaults
    assert UserRepository(session).get_by_email("trader@example.com") == user


def test_duplicate_email_is_rejected(session: Session) -> None:
    make_user(session, email="same@example.com")
    with pytest.raises(IntegrityError, match="uq_users_email"):
        make_user(session, email="same@example.com")


def test_strategy_names_are_unique_per_user(session: Session) -> None:
    alice, bob = make_user(session), make_user(session)
    strategies = StrategyRepository(session)
    strategies.add(user_id=alice.id, name="Breakout")
    strategies.add(user_id=bob.id, name="Breakout")  # same name, other user: fine

    with pytest.raises(IntegrityError, match="uq_strategies_user_id_name"):
        strategies.add(user_id=alice.id, name="Breakout")


def test_lookups_never_return_another_users_rows(session: Session) -> None:
    alice, bob = make_user(session), make_user(session)
    strategy = StrategyRepository(session).add(user_id=alice.id, name="Pullback")
    trade = add_trade(session, alice.id, strategy_id=strategy.id)
    entry = JournalEntryRepository(session).add(
        trade_id=trade.id, phase=JournalPhase.PRE, body="Waiting for the retest."
    )

    assert StrategyRepository(session).get(bob.id, strategy.id) is None
    assert TradeRepository(session).get(bob.id, trade.id) is None
    assert JournalEntryRepository(session).get(bob.id, entry.id) is None
    assert JournalEntryRepository(session).list_for_trade(bob.id, trade.id) == []
    assert TradeRepository(session).list(bob.id) == []

    assert TradeRepository(session).get(alice.id, trade.id) == trade
    assert JournalEntryRepository(session).list_for_trade(alice.id, trade.id) == [entry]


def test_trade_defaults_and_exact_decimals(session: Session) -> None:
    user = make_user(session)
    trade = add_trade(  # a sub-cent crypto price, at the full 8 decimal places
        session,
        user.id,
        asset_type=AssetType.CRYPTO,
        symbol="SHIB-USD",
        planned_entry=Decimal("0.00001234"),
        planned_stop=Decimal("0.00001100"),
        planned_target=Decimal("0.00001500"),
    )
    session.expire_all()  # force a reload from the database

    reloaded = TradeRepository(session).get(user.id, trade.id)
    assert reloaded is not None
    assert reloaded.status is TradeStatus.PLANNED
    assert reloaded.source is TradeSource.MANUAL
    assert reloaded.planned_entry == Decimal("0.00001234")
    assert isinstance(reloaded.planned_entry, Decimal)


def test_trade_moves_through_open_and_closed(session: Session) -> None:
    user = make_user(session)
    trades = TradeRepository(session)
    trade = add_trade(session, user.id)

    trade.status = TradeStatus.OPEN
    trade.entry_price = Decimal("100.50")
    trade.entry_at = datetime(2026, 10, 1, 14, 30, tzinfo=UTC)
    trade.quantity = Decimal("10")
    trades.save(trade)

    trade.status = TradeStatus.CLOSED
    trade.exit_price = Decimal("110.25")
    trade.exit_at = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)
    trade.fees = Decimal("1.00")
    trade.followed_plan = True
    trades.save(trade)

    assert trades.get(user.id, trade.id) == trade


def test_external_id_is_unique_per_user_and_source(session: Session) -> None:
    user = make_user(session)
    add_trade(session, user.id, source=TradeSource.WEBULL, external_id="ord-1")
    add_trade(session, user.id, source=TradeSource.TRADINGVIEW, external_id="ord-1")
    add_trade(session, user.id)  # NULL external_ids don't collide
    add_trade(session, user.id)

    with pytest.raises(IntegrityError, match="uq_trades_user_id_source_external_id"):
        add_trade(session, user.id, source=TradeSource.WEBULL, external_id="ord-1")


def test_journal_entries_are_listed_oldest_first(session: Session) -> None:
    user = make_user(session)
    trade = add_trade(session, user.id)
    journal = JournalEntryRepository(session)
    first = journal.add(trade_id=trade.id, phase=JournalPhase.PRE, body="Plan looks clean.")
    second = journal.add(trade_id=trade.id, phase=JournalPhase.DURING, body="Holding.")

    assert journal.list_for_trade(user.id, trade.id) == [first, second]


def test_deleting_a_trade_deletes_its_journal(session: Session) -> None:
    user = make_user(session)
    trade = add_trade(session, user.id)
    entry_id = (
        JournalEntryRepository(session)
        .add(trade_id=trade.id, phase=JournalPhase.POST, body="Exited at target.")
        .id
    )
    TradeRepository(session).delete(trade)
    session.expire_all()

    assert JournalEntryRepository(session).get(user.id, entry_id) is None
