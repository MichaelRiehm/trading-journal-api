"""Migrations and models stay in sync, and the migrations run both ways."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from conftest import run_alembic
from trading_journal.db.base import Base

TABLES = {"users", "strategies", "trades", "journal_entries"}


def test_models_match_migrations(engine: Engine) -> None:
    """Fails if a model changed without a migration (what `alembic check` reports).

    Autogenerate doesn't compare CHECK constraints; test_constraints.py covers those.
    """
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    assert diff == []


def test_upgrade_downgrade_round_trip(scratch_database: Engine) -> None:
    run_alembic(scratch_database, lambda cfg: command.upgrade(cfg, "head"))
    assert set(inspect(scratch_database).get_table_names()) >= TABLES

    run_alembic(scratch_database, lambda cfg: command.downgrade(cfg, "base"))
    assert set(inspect(scratch_database).get_table_names()) <= {"alembic_version"}

    run_alembic(scratch_database, lambda cfg: command.upgrade(cfg, "head"))
    assert set(inspect(scratch_database).get_table_names()) >= TABLES
