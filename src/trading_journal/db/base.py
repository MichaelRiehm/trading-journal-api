"""Declarative base, column conventions and shared mixins for all ORM models."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names, so Alembic migrations are reproducible.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Prices, quantities and fees: exact decimals. 8 places covers fractional crypto
# quantities and sub-cent prices. Never float.
MONEY = Numeric(20, 8)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012  # SQLAlchemy reads this class attribute
        Decimal: MONEY,
        datetime: DateTime(timezone=True),
    }


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """A VARCHAR column plus a CHECK constraint, storing the enum's values.

    Not a native Postgres ENUM: adding a value later is an ordinary migration.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=max(len(member.value) for member in enum_cls),
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )


class UUIDPrimaryKey:
    # UUIDv7: time-ordered (index friendly) and not guessable (ids don't leak).
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
