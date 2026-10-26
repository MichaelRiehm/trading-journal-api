"""Alembic environment: runs migrations against DATABASE_URL (from the app's Settings).

Tests pass an open connection in `config.attributes["connection"]` instead, so they
can migrate a throwaway test database.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine

import trading_journal.models  # noqa: F401  # registers every table on Base.metadata
from trading_journal.config import get_settings
from trading_journal.db.base import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("connection"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection: Connection | None = config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 5})
    with engine.connect() as conn:
        run_migrations(conn)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
