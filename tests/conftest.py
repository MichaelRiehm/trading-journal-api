"""Shared fixtures.

Integration tests use a real Postgres. Once per test session, a dedicated test
database is created, migrated with Alembic (so the migrations are tested too) and
dropped at the end. Each test runs inside a transaction that is rolled back, so
tests never see each other's data and need no cleanup.
"""

import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from trading_journal.config import get_settings
from trading_journal.main import create_app

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
_SAFE_DB_NAME = re.compile(r"^[a-z0-9_]+$")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _test_database_url() -> URL:
    settings = get_settings()
    if settings.test_database_url:
        return make_url(settings.test_database_url)
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_test")


def _admin_engine(url: URL) -> Engine:
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    return create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )


def create_database(url: URL) -> None:
    name = url.database or ""
    if not _SAFE_DB_NAME.match(name):
        raise ValueError(f"refusing to create test database with unsafe name {name!r}")
    admin = _admin_engine(url)
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:
        pytest.exit(
            f"Postgres is not reachable at {url.host}:{url.port}. "
            f"Start it with `make db` (or set TEST_DATABASE_URL).\n{exc}",
            returncode=2,
        )
    finally:
        admin.dispose()


def drop_database(url: URL) -> None:
    admin = _admin_engine(url)
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
    admin.dispose()


def run_alembic(engine: Engine, action: Callable[[Config], None]) -> None:
    config = Config(str(ALEMBIC_INI))
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        action(config)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = _test_database_url()
    create_database(url)
    test_engine = create_engine(url, connect_args={"connect_timeout": 5})
    run_alembic(test_engine, lambda cfg: command.upgrade(cfg, "head"))
    yield test_engine
    test_engine.dispose()
    drop_database(url)


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test.

    `create_savepoint` means code under test may call commit(): it only releases a
    SAVEPOINT, and the outer transaction is still rolled back at the end.
    """
    with engine.connect() as conn:
        outer = conn.begin()
        db_session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db_session
        finally:
            db_session.close()
            outer.rollback()


@pytest.fixture
def scratch_database() -> Iterator[Engine]:
    """An empty, unmigrated database for tests that run migrations themselves."""
    url = _test_database_url()
    url = url.set(database=f"{url.database}_scratch")
    create_database(url)
    scratch_engine = create_engine(url, connect_args={"connect_timeout": 5})
    yield scratch_engine
    scratch_engine.dispose()
    drop_database(url)
