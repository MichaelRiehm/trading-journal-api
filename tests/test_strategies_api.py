import pytest
from fastapi.testclient import TestClient

from api_helpers import create_strategy, create_trade, registered_headers


def test_create_and_read(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)

    response = api_client.post(
        "/strategies",
        json={"name": "  Breakout  ", "description": "New highs on volume"},
        headers=headers,
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Breakout"  # trimmed
    assert created["description"] == "New highs on volume"
    fetched = api_client.get(f"/strategies/{created['id']}", headers=headers)
    assert fetched.json() == created


def test_list_is_sorted_by_name_and_only_mine(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    _, other_headers = registered_headers(api_client)
    for name in ["Pullback", "Breakout", "Gap fill"]:
        create_strategy(api_client, headers, name)
    create_strategy(api_client, other_headers, "Someone else's")

    response = api_client.get("/strategies", headers=headers)

    assert [s["name"] for s in response.json()] == ["Breakout", "Gap fill", "Pullback"]


def test_duplicate_name_is_a_conflict(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    create_strategy(api_client, headers, "Breakout")

    response = api_client.post("/strategies", json={"name": "Breakout"}, headers=headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "You already have a strategy with this name"}


def test_same_name_is_fine_for_another_user(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    _, other_headers = registered_headers(api_client)
    create_strategy(api_client, headers, "Breakout")

    create_strategy(api_client, other_headers, "Breakout")  # asserts 201


def test_update_name_and_clear_description(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    strategy = api_client.post(
        "/strategies", json={"name": "Breakout", "description": "old"}, headers=headers
    ).json()

    response = api_client.patch(
        f"/strategies/{strategy['id']}",
        json={"name": "Breakout v2", "description": None},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Breakout v2"
    assert response.json()["description"] is None


def test_rename_to_existing_name_is_a_conflict(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    create_strategy(api_client, headers, "Breakout")
    other = create_strategy(api_client, headers, "Pullback")

    response = api_client.patch(
        f"/strategies/{other['id']}", json={"name": "Breakout"}, headers=headers
    )

    assert response.status_code == 409


def test_renaming_to_its_own_name_is_fine(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    strategy = create_strategy(api_client, headers, "Breakout")

    response = api_client.patch(
        f"/strategies/{strategy['id']}", json={"name": "Breakout"}, headers=headers
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": None}, id="null-name"),
        pytest.param({"name": "   "}, id="blank-name"),
        pytest.param({"name": "x" * 101}, id="long-name"),
    ],
)
def test_invalid_update_is_rejected(api_client: TestClient, body: dict[str, object]) -> None:
    _, headers = registered_headers(api_client)
    strategy = create_strategy(api_client, headers)

    response = api_client.patch(f"/strategies/{strategy['id']}", json=body, headers=headers)

    assert response.status_code == 422


def test_delete(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    strategy = create_strategy(api_client, headers)

    response = api_client.delete(f"/strategies/{strategy['id']}", headers=headers)

    assert response.status_code == 204
    assert api_client.get(f"/strategies/{strategy['id']}", headers=headers).status_code == 404


def test_strategy_with_trades_cannot_be_deleted(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    strategy = create_strategy(api_client, headers)
    create_trade(api_client, headers, strategy_id=strategy["id"])

    response = api_client.delete(f"/strategies/{strategy['id']}", headers=headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "Strategy has trades. Reassign or delete them first"}
