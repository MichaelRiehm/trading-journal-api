from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_helpers import create_strategy, create_trade, plan_payload, registered_headers

# --- create ---------------------------------------------------------------------


def test_create_returns_a_plan_with_derived_fields(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)

    response = api_client.post("/trades", json=plan_payload(), headers=headers)

    assert response.status_code == 201
    trade = response.json()
    assert trade["status"] == "planned"
    assert trade["source"] == "manual"
    assert trade["planned_entry"] == "100.00000000"  # Decimals go out as strings
    assert trade["r_per_share"] == "5.00000000"
    assert trade["exposure"] == "bullish"
    assert trade["pnl"] is None
    assert trade["r_multiple"] is None
    assert trade["hold_time"] is None


def test_symbol_is_normalized(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)

    trade = create_trade(api_client, headers, symbol="  brk.b ")

    assert trade["symbol"] == "BRK.B"


def test_inverse_etf_is_a_bearish_long(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)

    trade = create_trade(api_client, headers, symbol="SQQQ", asset_type="etf", leverage_factor=-3)

    assert trade["side"] == "long"
    assert trade["leverage_factor"] == -3
    assert trade["exposure"] == "bearish"


def test_short_is_bearish(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)

    trade = create_trade(api_client, headers, side="short", planned_stop="105")

    assert trade["exposure"] == "bearish"


@pytest.mark.parametrize(
    "extra",
    [{"pnl": "1000000"}, {"status": "closed"}, {"r_multiple": "10"}, {"planed_stop": "90"}],
    ids=["pnl", "status", "r_multiple", "typo"],
)
def test_derived_or_unknown_fields_are_rejected(
    api_client: TestClient, extra: dict[str, str]
) -> None:
    _, headers = registered_headers(api_client)

    response = api_client.post("/trades", json={**plan_payload(), **extra}, headers=headers)

    assert response.status_code == 422


def test_patch_with_a_typo_is_rejected_not_ignored(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)

    response = api_client.patch(
        f"/trades/{trade['id']}", json={"planed_stop": "90"}, headers=headers
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        pytest.param(
            {"planned_stop": "105"},
            "For a long trade, planned_stop must be below planned_entry",
            id="long-stop-above-entry",
        ),
        pytest.param(
            {"side": "short", "planned_stop": "95"},
            "For a short trade, planned_stop must be above planned_entry",
            id="short-stop-below-entry",
        ),
        pytest.param(
            {"leverage_factor": 2},
            "leverage_factor is only allowed for ETFs",
            id="leverage-on-a-stock",
        ),
    ],
)
def test_business_rule_violations(
    api_client: TestClient, overrides: dict[str, Any], detail: str
) -> None:
    _, headers = registered_headers(api_client)

    response = api_client.post("/trades", json=plan_payload(**overrides), headers=headers)

    assert response.status_code == 422
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"asset_type": "etf", "leverage_factor": 4}, id="leverage-not-allowed"),
        pytest.param({"planned_entry": "-1"}, id="negative-price"),
        pytest.param({"planned_entry": "0.000000001"}, id="too-many-decimals"),
        pytest.param({"planned_entry": "1234567890123"}, id="too-many-digits"),
        pytest.param({"symbol": "AA PL"}, id="bad-symbol"),
        pytest.param({"asset_type": "option"}, id="unknown-asset-type"),
        pytest.param({"thesis": "  "}, id="blank-thesis"),
        pytest.param({"thesis": None}, id="missing-thesis"),
    ],
)
def test_schema_violations(api_client: TestClient, overrides: dict[str, Any]) -> None:
    _, headers = registered_headers(api_client)

    response = api_client.post("/trades", json=plan_payload(**overrides), headers=headers)

    assert response.status_code == 422


def test_strategy_must_be_mine(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    _, other_headers = registered_headers(api_client)
    theirs = create_strategy(api_client, other_headers)

    response = api_client.post(
        "/trades", json=plan_payload(strategy_id=theirs["id"]), headers=headers
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "strategy_id does not match any of your strategies"}


def test_duplicate_external_id_is_a_conflict(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    create_trade(api_client, headers, source="tradingview", external_id="alert-42")

    duplicate = api_client.post(
        "/trades",
        json=plan_payload(source="tradingview", external_id="alert-42"),
        headers=headers,
    )
    other_source = api_client.post(
        "/trades", json=plan_payload(source="webull", external_id="alert-42"), headers=headers
    )

    assert duplicate.status_code == 409
    assert other_source.status_code == 201


# --- update ---------------------------------------------------------------------


def test_patch_changes_only_sent_fields(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)

    response = api_client.patch(
        f"/trades/{trade['id']}", json={"planned_target": "120"}, headers=headers
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["planned_target"] == "120.00000000"
    assert updated["thesis"] == trade["thesis"]


def test_patch_validates_the_merged_plan(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)  # long, entry 100, stop 95

    # Flipping to short without moving the stop leaves the stop on the wrong side.
    response = api_client.patch(f"/trades/{trade['id']}", json={"side": "short"}, headers=headers)
    after = api_client.get(f"/trades/{trade['id']}", headers=headers).json()

    assert response.status_code == 422
    assert after == trade


def test_patch_null_for_required_field_is_rejected(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)

    response = api_client.patch(f"/trades/{trade['id']}", json={"symbol": None}, headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize("status", ["open", "closed", "cancelled"])
def test_plan_is_locked_after_planning(api_client: TestClient, status: str) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status=status)

    response = api_client.patch(
        f"/trades/{trade['id']}", json={"planned_stop": "90"}, headers=headers
    )

    assert response.status_code == 409


@pytest.mark.parametrize("status", ["planned", "open", "closed"])
def test_strategy_can_be_reassigned_in_any_status(api_client: TestClient, status: str) -> None:
    _, headers = registered_headers(api_client)
    strategy = create_strategy(api_client, headers)
    trade = create_trade(api_client, headers, status=status)

    assigned = api_client.patch(
        f"/trades/{trade['id']}", json={"strategy_id": strategy["id"]}, headers=headers
    )
    untouched = api_client.patch(f"/trades/{trade['id']}", json={}, headers=headers)
    cleared = api_client.patch(
        f"/trades/{trade['id']}", json={"strategy_id": None}, headers=headers
    )

    assert assigned.json()["strategy_id"] == strategy["id"]
    assert untouched.json()["strategy_id"] == strategy["id"]  # omitted = unchanged
    assert cleared.json()["strategy_id"] is None  # null = cleared


# --- delete ---------------------------------------------------------------------


@pytest.mark.parametrize("status", ["planned", "closed"])
def test_delete(api_client: TestClient, status: str) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status=status)

    response = api_client.delete(f"/trades/{trade['id']}", headers=headers)

    assert response.status_code == 204
    assert api_client.get(f"/trades/{trade['id']}", headers=headers).status_code == 404


# --- list -------------------------------------------------------------------------


def test_filters(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    strategy = create_strategy(api_client, headers)
    aapl = create_trade(api_client, headers, strategy_id=strategy["id"])
    msft_open = create_trade(api_client, headers, symbol="MSFT", status="open")
    short = create_trade(api_client, headers, symbol="TSLA", side="short", planned_stop="105")
    etf = create_trade(api_client, headers, symbol="SQQQ", asset_type="etf", leverage_factor=-3)

    def ids(**params: str) -> list[str]:
        response = api_client.get("/trades", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [t["id"] for t in response.json()["items"]]

    assert ids(status="open") == [msft_open["id"]]
    assert ids(strategy_id=strategy["id"]) == [aapl["id"]]
    assert ids(symbol="msft") == [msft_open["id"]]  # normalized like on create
    assert ids(side="short") == [short["id"]]
    assert ids(asset_type="etf") == [etf["id"]]
    assert ids(status="planned", side="long") == [etf["id"], aapl["id"]]  # newest first


def test_list_excludes_other_users(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    _, other_headers = registered_headers(api_client)
    create_trade(api_client, other_headers)

    response = api_client.get("/trades", headers=headers)

    assert response.json() == {"items": [], "next_cursor": None}


def test_keyset_pagination_has_no_gaps_or_repeats(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    created = [create_trade(api_client, headers)["id"] for _ in range(5)]
    newest_first = list(reversed(created))

    first = api_client.get("/trades", params={"limit": 2}, headers=headers).json()
    # A trade created between pages must not shift the later pages.
    create_trade(api_client, headers)
    second = api_client.get(
        "/trades", params={"limit": 2, "cursor": first["next_cursor"]}, headers=headers
    ).json()
    third = api_client.get(
        "/trades", params={"limit": 2, "cursor": second["next_cursor"]}, headers=headers
    ).json()

    pages = [first, second, third]
    seen = [t["id"] for page in pages for t in page["items"]]
    assert seen == newest_first
    assert first["next_cursor"] == newest_first[1]
    assert third["next_cursor"] is None


@pytest.mark.parametrize("limit", ["0", "201", "abc"])
def test_invalid_limit(api_client: TestClient, limit: str) -> None:
    _, headers = registered_headers(api_client)

    response = api_client.get("/trades", params={"limit": limit}, headers=headers)

    assert response.status_code == 422
