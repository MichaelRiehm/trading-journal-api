"""Every (status x action) pair: the 3 legal moves succeed, the other 9 return 409."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_helpers import CLOSE_BODY, OPEN_BODY, create_trade, registered_headers
from trading_journal.domain.enums import TradeStatus
from trading_journal.domain.lifecycle import ALLOWED_TRANSITIONS

STATUSES = ["planned", "open", "closed", "cancelled"]
ACTIONS: dict[str, tuple[TradeStatus, dict[str, Any] | None]] = {
    "open": (TradeStatus.OPEN, OPEN_BODY),
    "close": (TradeStatus.CLOSED, CLOSE_BODY),
    "cancel": (TradeStatus.CANCELLED, None),
}
LEGAL = {("planned", "open"), ("planned", "cancel"), ("open", "close")}


def test_matrix_matches_the_domain_table() -> None:
    # Guards against the test and the code drifting apart.
    from_table = {
        (current.value, action)
        for current, targets in ALLOWED_TRANSITIONS.items()
        for action, (target, _) in ACTIONS.items()
        if target in targets
    }
    assert from_table == LEGAL


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("start", STATUSES)
def test_transition(api_client: TestClient, start: str, action: str) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status=start)
    target, body = ACTIONS[action]

    response = api_client.post(f"/trades/{trade['id']}/{action}", json=body, headers=headers)
    after = api_client.get(f"/trades/{trade['id']}", headers=headers).json()

    if (start, action) in LEGAL:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target.value
        assert after == response.json()
    else:
        assert response.status_code == 409
        assert response.json()["detail"] == f"Cannot {action} a trade that is {start}"
        assert after == trade  # nothing changed


def test_open_records_the_entry(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)

    trade = create_trade(api_client, headers, status="open")

    assert trade["entry_price"] == "100.00000000"
    assert trade["quantity"] == "10.00000000"
    assert trade["entry_at"].startswith("2026-10-01T14:30:00")
    assert trade["pnl"] is None
    assert trade["r_multiple"] is None


def test_close_computes_the_derived_values(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)

    trade = create_trade(api_client, headers, status="closed")

    # Long 10 @ 100 -> 110, fees 2: (110 - 100) x 10 - 2 = 98. R = 5/share: 9.8 / 5 = 1.96R.
    assert trade["pnl"] == "98.00000000"
    assert trade["r_per_share"] == "5.00000000"
    assert trade["r_multiple"] == "1.9600"
    assert trade["hold_time"] == "P2DT4H30M"
    assert trade["followed_plan"] is True


def test_entry_time_defaults_to_now(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)

    response = api_client.post(
        f"/trades/{trade['id']}/open",
        json={"entry_price": "100", "quantity": "1"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["entry_at"] is not None


@pytest.mark.parametrize(
    ("action", "body", "message"),
    [
        pytest.param(
            "open",
            {**OPEN_BODY, "entry_at": "2999-01-01T00:00:00Z"},
            "entry_at cannot be in the future",
            id="future-entry",
        ),
        pytest.param(
            "open",
            {**OPEN_BODY, "entry_at": "2026-10-01T14:30:00"},
            None,  # Pydantic's own 422: a timezone is required
            id="naive-datetime",
        ),
    ],
)
def test_open_validation(
    api_client: TestClient, action: str, body: dict[str, Any], message: str | None
) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)

    response = api_client.post(f"/trades/{trade['id']}/{action}", json=body, headers=headers)

    assert response.status_code == 422
    if message:
        assert response.json()["detail"] == message


def test_exit_before_entry_is_rejected(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status="open")

    response = api_client.post(
        f"/trades/{trade['id']}/close",
        json={**CLOSE_BODY, "exit_at": "2026-09-30T00:00:00Z"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "exit_at cannot be before entry_at"


def test_close_requires_followed_plan(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status="open")
    body = {k: v for k, v in CLOSE_BODY.items() if k != "followed_plan"}

    response = api_client.post(f"/trades/{trade['id']}/close", json=body, headers=headers)

    assert response.status_code == 422
