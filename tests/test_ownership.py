"""The ownership pattern every resource route follows from Stage 3 on.

A route takes `CurrentUser`, the repository query is scoped by `user.id`, and a miss raises
NotFoundError. So another user's row and a row that doesn't exist produce the same 404, and
ids can't be probed. The probe route is registered only on the test app.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api_helpers import registered_headers
from trading_journal.api.deps import CurrentUser, SessionDep
from trading_journal.domain.errors import NotFoundError
from trading_journal.repositories import StrategyRepository


@pytest.fixture
def probe_client(app: FastAPI) -> Iterator[TestClient]:
    @app.get("/_probe/strategies/{strategy_id}")
    def get_strategy(
        strategy_id: uuid.UUID, user: CurrentUser, session: SessionDep
    ) -> dict[str, str]:
        strategy = StrategyRepository(session).get(user.id, strategy_id)
        if strategy is None:
            raise NotFoundError("Strategy")
        return {"name": strategy.name}

    with TestClient(app) as client:
        yield client


def test_owner_can_read_own_strategy(probe_client: TestClient, session: Session) -> None:
    owner, headers = registered_headers(probe_client)
    strategy = StrategyRepository(session).add(user_id=uuid.UUID(owner["id"]), name="Breakout")

    response = probe_client.get(f"/_probe/strategies/{strategy.id}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"name": "Breakout"}


def test_other_users_strategy_looks_exactly_like_a_missing_one(
    probe_client: TestClient, session: Session
) -> None:
    owner, _ = registered_headers(probe_client)
    _, intruder_headers = registered_headers(probe_client)
    strategy = StrategyRepository(session).add(user_id=uuid.UUID(owner["id"]), name="Breakout")

    someone_elses = probe_client.get(f"/_probe/strategies/{strategy.id}", headers=intruder_headers)
    missing = probe_client.get(f"/_probe/strategies/{uuid.uuid7()}", headers=intruder_headers)

    assert someone_elses.status_code == 404
    assert someone_elses.status_code == missing.status_code
    assert someone_elses.json() == missing.json() == {"detail": "Strategy not found"}


def test_probe_requires_authentication(probe_client: TestClient) -> None:
    response = probe_client.get(f"/_probe/strategies/{uuid.uuid7()}")

    assert response.status_code == 401
