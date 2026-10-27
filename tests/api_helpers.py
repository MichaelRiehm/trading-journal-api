"""Helpers for API tests: register a user and get auth headers through the real endpoints."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

PASSWORD = "correct horse battery staple"


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:8]}@example.com"


def register(client: TestClient, email: str | None = None, password: str = PASSWORD) -> Any:
    response = client.post(
        "/auth/register", json={"email": email or unique_email(), "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post("/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def registered_headers(client: TestClient) -> tuple[Any, dict[str, str]]:
    """Register a fresh user and return (user JSON, auth headers)."""
    user = register(client)
    return user, login(client, user["email"])


def create_strategy(client: TestClient, headers: dict[str, str], name: str = "Breakout") -> Any:
    response = client.post("/strategies", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def plan_payload(**overrides: Any) -> dict[str, Any]:
    """A valid long stock plan: entry 100, stop 95 (R = 5 per share), target 115."""
    payload: dict[str, Any] = {
        "symbol": "AAPL",
        "asset_type": "stock",
        "side": "long",
        "planned_entry": "100.00",
        "planned_stop": "95.00",
        "planned_target": "115.00",
        "thesis": "Breakout above the 50-day high on volume.",
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


OPEN_BODY = {"entry_price": "100.00", "quantity": "10", "entry_at": "2026-10-01T14:30:00Z"}
CLOSE_BODY = {
    "exit_price": "110.00",
    "exit_at": "2026-10-03T19:00:00Z",
    "fees": "2.00",
    "followed_plan": True,
}


def create_trade(
    client: TestClient, headers: dict[str, str], status: str = "planned", **overrides: Any
) -> Any:
    """Create a trade through the API and walk it to `status` with the standard bodies."""
    response = client.post("/trades", json=plan_payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    trade = response.json()
    all_steps: dict[str, list[tuple[str, dict[str, Any] | None]]] = {
        "planned": [],
        "open": [("open", OPEN_BODY)],
        "closed": [("open", OPEN_BODY), ("close", CLOSE_BODY)],
        "cancelled": [("cancel", None)],
    }
    for action, body in all_steps[status]:
        response = client.post(f"/trades/{trade['id']}/{action}", json=body, headers=headers)
        assert response.status_code == 200, response.text
        trade = response.json()
    return trade
