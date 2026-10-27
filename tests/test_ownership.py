"""Another user's data is indistinguishable from data that doesn't exist: 404, never 403.

Every strategy and trade endpoint that takes an id is checked. Services query by
(user.id, id), so "not yours" and "doesn't exist" are the same code path. These tests
make sure no endpoint skips that, and that the row is untouched afterwards.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_helpers import CLOSE_BODY, OPEN_BODY, create_strategy, create_trade, registered_headers

ENDPOINTS: list[tuple[str, str, str, dict[str, Any] | None]] = [
    # (resource, method, path suffix, body)
    ("strategies", "GET", "", None),
    ("strategies", "PATCH", "", {"name": "Hijacked"}),
    ("strategies", "DELETE", "", None),
    ("trades", "GET", "", None),
    ("trades", "PATCH", "", {"planned_target": "200"}),
    ("trades", "DELETE", "", None),
    ("trades", "POST", "/open", OPEN_BODY),
    ("trades", "POST", "/close", CLOSE_BODY),
    ("trades", "POST", "/cancel", None),
]


@pytest.mark.parametrize(
    ("resource", "method", "suffix", "body"),
    ENDPOINTS,
    ids=[f"{m} /{r}/{{id}}{s}" for r, m, s, _ in ENDPOINTS],
)
def test_other_users_row_looks_exactly_like_a_missing_one(
    api_client: TestClient,
    resource: str,
    method: str,
    suffix: str,
    body: dict[str, Any] | None,
) -> None:
    _, owner = registered_headers(api_client)
    _, intruder = registered_headers(api_client)
    row = (
        create_strategy(api_client, owner)
        if resource == "strategies"
        else create_trade(api_client, owner)
    )

    def call(row_id: str) -> Any:
        return api_client.request(
            method, f"/{resource}/{row_id}{suffix}", json=body, headers=intruder
        )

    someone_elses = call(row["id"])
    missing = call(str(uuid.uuid7()))

    assert someone_elses.status_code == 404
    assert (someone_elses.status_code, someone_elses.json()) == (
        missing.status_code,
        missing.json(),
    )
    # And nothing happened to the owner's row.
    after = api_client.get(f"/{resource}/{row['id']}", headers=owner)
    assert after.status_code == 200
    assert after.json() == row


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/strategies"), ("POST", "/strategies"), ("GET", "/trades"), ("POST", "/trades")],
)
def test_collection_endpoints_require_authentication(
    api_client: TestClient, method: str, path: str
) -> None:
    response = api_client.request(method, path, json={})

    assert response.status_code == 401
