import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.db.base import Base, Timestamps, UUIDPrimaryKey, str_enum
from trading_journal.domain.enums import AssetType, Side, TradeSource, TradeStatus

# Which fields each status requires. Illegal states can't be stored, even if a bug
# in the service layer tries to.
_NO_ENTRY = "entry_price IS NULL AND entry_at IS NULL AND quantity IS NULL"
_NO_EXIT = "exit_price IS NULL AND exit_at IS NULL AND fees IS NULL AND followed_plan IS NULL"
_ENTRY = "entry_price IS NOT NULL AND entry_at IS NOT NULL AND quantity IS NOT NULL"
_EXIT = (
    "exit_price IS NOT NULL AND exit_at IS NOT NULL AND fees IS NOT NULL"
    " AND followed_plan IS NOT NULL"
)
_STATUS_FIELDS = (
    f"(status IN ('planned', 'cancelled') AND {_NO_ENTRY} AND {_NO_EXIT})"
    f" OR (status = 'open' AND {_ENTRY} AND {_NO_EXIT})"
    f" OR (status = 'closed' AND {_ENTRY} AND {_EXIT})"
)


class Trade(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "trades"
    __table_args__ = (
        # The strategy must belong to the same user as the trade. A strategy that
        # still has trades can't be deleted.
        ForeignKeyConstraint(
            ["strategy_id", "user_id"],
            ["strategies.id", "strategies.user_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("user_id", "source", "external_id"),
        CheckConstraint(
            "planned_entry > 0 AND planned_stop > 0 AND planned_target > 0"
            " AND (entry_price IS NULL OR entry_price > 0)"
            " AND (exit_price IS NULL OR exit_price > 0)",
            name="prices_positive",
        ),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        CheckConstraint("fees IS NULL OR fees >= 0", name="fees_non_negative"),
        CheckConstraint(
            "leverage_factor IS NULL OR leverage_factor IN (2, 3, -2, -3)",
            name="leverage_factor_allowed",
        ),
        CheckConstraint(
            "(side = 'long' AND planned_stop < planned_entry)"
            " OR (side = 'short' AND planned_stop > planned_entry)",
            name="stop_on_losing_side",
        ),
        CheckConstraint(
            "exit_at IS NULL OR entry_at IS NULL OR exit_at >= entry_at",
            name="exit_after_entry",
        ),
        CheckConstraint(_STATUS_FIELDS, name="status_fields"),
        Index("ix_trades_user_id_status", "user_id", "status"),
        Index("ix_trades_user_id_exit_at", "user_id", "exit_at"),
        Index("ix_trades_strategy_id", "strategy_id"),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    strategy_id: Mapped[uuid.UUID | None]

    # The plan, required at creation.
    symbol: Mapped[str] = mapped_column(String(32))
    asset_type: Mapped[AssetType] = mapped_column(str_enum(AssetType, "asset_type"))
    # 2, 3, -2 or -3 for leveraged and inverse ETFs; None for unleveraged.
    leverage_factor: Mapped[int | None] = mapped_column(SmallInteger)
    side: Mapped[Side] = mapped_column(str_enum(Side, "side"))
    status: Mapped[TradeStatus] = mapped_column(
        str_enum(TradeStatus, "status"),
        default=TradeStatus.PLANNED,
        server_default=TradeStatus.PLANNED.value,
    )
    planned_entry: Mapped[Decimal]
    planned_stop: Mapped[Decimal]
    planned_target: Mapped[Decimal]
    thesis: Mapped[str] = mapped_column(Text)

    # Set when the trade is opened.
    entry_price: Mapped[Decimal | None]
    entry_at: Mapped[datetime | None]
    quantity: Mapped[Decimal | None]

    # Set when the trade is closed.
    exit_price: Mapped[Decimal | None]
    exit_at: Mapped[datetime | None]
    fees: Mapped[Decimal | None]
    followed_plan: Mapped[bool | None]

    source: Mapped[TradeSource] = mapped_column(
        str_enum(TradeSource, "source"),
        default=TradeSource.MANUAL,
        server_default=TradeSource.MANUAL.value,
    )
    # For idempotent imports (Phase 3): unique per user and source.
    external_id: Mapped[str | None] = mapped_column(String(128))
