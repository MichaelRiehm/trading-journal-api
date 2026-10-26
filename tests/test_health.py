from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from trading_journal.db.session import get_session
from trading_journal.main import create_app


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _client_with_engine(engine: Engine) -> TestClient:
    app = create_app()

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


def test_ready_when_database_is_up(engine: Engine) -> None:
    with _client_with_engine(engine) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_not_ready_when_database_is_down() -> None:
    # Port 1 on localhost refuses connections immediately.
    unreachable = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        connect_args={"connect_timeout": 2},
    )
    with _client_with_engine(unreachable) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
