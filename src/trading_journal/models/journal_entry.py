import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.db.base import Base, Timestamps, UUIDPrimaryKey, str_enum
from trading_journal.domain.enums import JournalPhase


class JournalEntry(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (Index("ix_journal_entries_trade_id_created_at", "trade_id", "created_at"),)
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    # Ownership follows the trade: no user_id of its own.
    trade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"))
    phase: Mapped[JournalPhase] = mapped_column(str_enum(JournalPhase, "phase"))
    body: Mapped[str] = mapped_column(Text)
