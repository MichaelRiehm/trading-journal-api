"""Small helpers that build valid rows for tests, with overridable fields."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from trading_journal.domain.enums import AssetType, Side
from trading_journal.models import Trade, User
from trading_journal.repositories import TradeRepository, UserRepository


def make_user(session: Session, email: str | None = None) -> User:
    return UserRepository(session).add(
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
    )


def planned_trade(user_id: uuid.UUID, **overrides: Any) -> Trade:
    fields: dict[str, Any] = {
        "user_id": user_id,
        "symbol": "AAPL",
        "asset_type": AssetType.STOCK,
        "side": Side.LONG,
        "planned_entry": Decimal("100.00"),
        "planned_stop": Decimal("95.00"),
        "planned_target": Decimal("115.00"),
        "thesis": "Breakout above the 50-day high on volume.",
    }
    fields.update(overrides)
    return Trade(**fields)


def add_trade(session: Session, user_id: uuid.UUID, **overrides: Any) -> Trade:
    return TradeRepository(session).add(planned_trade(user_id, **overrides))
