"""Every error is an RFC 9457 problem (ADR 0013)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_helpers import PASSWORD, create_trade, registered_headers, unique_email
from trading_journal.main import create_app

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "request_id"}


def assert_problem(response: Any, status: int, detail: str | None = None) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert body.keys() >= PROBLEM_KEYS
    assert body["type"] == "about:blank"
    assert body["status"] == status
    assert body["instance"] == response.request.url.path
    assert body["request_id"] == response.headers["X-Request-ID"]
    if detail is not None:
        assert body["detail"] == detail
    return body


def test_not_found(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    response = api_client.get(f"/trades/{uuid.uuid4()}", headers=headers)
    body = assert_problem(response, 404, "Trade not found")
    assert body["title"] == "Not Found"


def test_conflict(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)
    response = api_client.post(
        f"/trades/{trade['id']}/close",
        json={"exit_price": "1", "followed_plan": True},
        headers=headers,
    )
    assert_problem(response, 409, "Cannot close a trade that is planned")


def test_domain_invalid_input(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    response = api_client.post(
        "/trades",
        json={
            "symbol": "AAPL",
            "asset_type": "stock",
            "side": "long",
            "planned_entry": "100",
            "planned_stop": "105",
            "planned_target": "115",
            "thesis": "x",
        },
        headers=headers,
    )
    body = assert_problem(
        response, 422, "For a long trade, planned_stop must be below planned_entry"
    )
    assert "errors" not in body  # only request validation lists field errors


def test_unauthenticated_keeps_www_authenticate(client: TestClient) -> None:
    response = client.get("/users/me")
    assert_problem(response, 401, "Could not validate credentials")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_validation_errors_list_fields_but_never_echo_input(client: TestClient) -> None:
    secret = "short-pw"  # under the 12-character minimum
    response = client.post("/auth/register", json={"email": unique_email(), "password": secret})
    body = assert_problem(response, 422, "The request is invalid; see errors")
    assert body["errors"] == [
        {
            "loc": ["body", "password"],
            "msg": "String should have at least 12 characters",
            "type": "string_too_short",
        }
    ]
    assert secret not in response.text


def test_unknown_route_and_wrong_method(client: TestClient) -> None:
    assert_problem(client.get("/nope"), 404, "Not Found")
    response = client.delete("/health")
    assert_problem(response, 405, "Method Not Allowed")
    assert response.headers["Allow"] == "GET"


def test_unhandled_errors_are_a_generic_500() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    with TestClient(app) as client:
        response = client.get("/boom")
    assert_problem(response, 500, "Internal server error")
    assert "hunter2" not in response.text


@pytest.mark.parametrize(
    ("sent", "echoed"),
    [
        ("abc-123.DEF_456", True),
        ("x" * 65, False),  # too long
        ("bad id", False),  # a space
        ("inject\\nnewline", False),
    ],
)
def test_request_id_header(client: TestClient, sent: str, echoed: bool) -> None:
    response = client.get("/health", headers={"X-Request-ID": sent})
    assert (response.headers["X-Request-ID"] == sent) is echoed
    assert len(response.headers["X-Request-ID"]) <= 64


def test_login_failure_is_a_problem(api_client: TestClient) -> None:
    # api_client, not client: this one queries the database.
    response = api_client.post(
        "/auth/token", data={"username": unique_email(), "password": PASSWORD}
    )
    assert_problem(response, 401, "Incorrect email or password")
