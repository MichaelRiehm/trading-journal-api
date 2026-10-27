"""Migrations and models stay in sync, and the migrations run both ways."""

from datetime import UTC, datetime

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

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


def test_0003_backfills_cancelled_at_from_updated_at(scratch_database: Engine) -> None:
    run_alembic(scratch_database, lambda cfg: command.upgrade(cfg, "0002"))
    with scratch_database.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash)"
                " VALUES (gen_random_uuid(), 'old@example.com', 'x')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO trades (id, user_id, symbol, asset_type, side, status, planned_entry,"
                " planned_stop, planned_target, thesis, updated_at)"
                " SELECT gen_random_uuid(), id, 'AAPL', 'stock', 'long', status, 100, 95, 115,"
                " 'old', '2026-10-01T12:00:00Z' FROM users, (VALUES ('planned'), ('cancelled'))"
                " AS s(status)"
            )
        )

    run_alembic(scratch_database, lambda cfg: command.upgrade(cfg, "0003"))
    with scratch_database.connect() as conn:
        result = conn.execute(text("SELECT status, cancelled_at FROM trades"))
        rows: dict[str, datetime | None] = dict(result.all())
    assert rows == {"planned": None, "cancelled": datetime(2026, 10, 1, 12, tzinfo=UTC)}
