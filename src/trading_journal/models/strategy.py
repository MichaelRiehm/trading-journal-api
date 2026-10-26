import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.db.base import Base, Timestamps, UUIDPrimaryKey


class Strategy(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "strategies"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        # Target for the composite foreign key on trades (strategy_id, user_id): it lets
        # the database guarantee a trade never points at another user's strategy.
        UniqueConstraint("id", "user_id"),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
