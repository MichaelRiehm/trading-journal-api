from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from trading_journal.db.base import Base, Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are stored lowercased, so the plain unique constraint is case-insensitive.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
