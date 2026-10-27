"""Structured logs: JSON lines, request ids, and no secrets (ADR 0014)."""

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from api_helpers import PASSWORD, login, register, unique_email
from trading_journal.db.session import get_engine
from trading_journal.logging_config import JsonFormatter, RequestContext, request_context
from trading_journal.models import User


class _JsonCapture(logging.Handler):
    """Formats each record as it is emitted, while the request context is still set."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def logs(app: FastAPI) -> Iterator[_JsonCapture]:
    # After `app`: create_app() reconfigures logging, which would drop a handler added earlier.
    handler = _JsonCapture()
    root = logging.getLogger()
    root.addHandler(handler)
    yield handler
    root.removeHandler(handler)


def access_lines(logs: _JsonCapture) -> list[dict[str, Any]]:
    entries = [json.loads(line) for line in logs.lines]
    return [e for e in entries if e["logger"] == "trading_journal.request"]


def test_formatter_writes_one_json_object_with_allowlisted_fields() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.status = 200
    record.password = "never"  # not on the allowlist
    token = request_context.set(RequestContext(request_id="req-1", user_id="u-1"))
    try:
        entry = json.loads(JsonFormatter().format(record))
    finally:
        request_context.reset(token)
    assert entry.keys() == {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "user_id",
        "status",
    }
    assert entry["message"] == "hello world"
    assert entry["timestamp"].endswith("+00:00")


def test_one_access_line_per_request(api_client: TestClient, logs: _JsonCapture) -> None:
    response = api_client.get("/health?verbose=1", headers={"X-Request-ID": "trace-me"})
    [line] = access_lines(logs)
    assert line["request_id"] == "trace-me" == response.headers["X-Request-ID"]
    assert line["method"] == "GET"
    assert line["path"] == "/health"  # no query string
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert "user_id" not in line


def test_access_line_carries_the_user_once_authenticated(
    api_client: TestClient, logs: _JsonCapture
) -> None:
    user = register(api_client)
    headers = login(api_client, user["email"])
    api_client.get("/users/me", headers=headers)
    assert access_lines(logs)[-1]["user_id"] == user["id"]


def test_unhandled_errors_are_logged_with_a_traceback(app: FastAPI, logs: _JsonCapture) -> None:
    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app) as client:
        response = client.get("/boom")
    entries = [json.loads(line) for line in logs.lines]
    [error] = [e for e in entries if e["level"] == "ERROR"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert "RuntimeError: kaboom" in error["exception"]
    assert access_lines(logs)[-1]["status"] == 500


def test_no_secrets_in_the_logs(
    api_client: TestClient, logs: _JsonCapture, session: Session
) -> None:
    email = unique_email()
    register(api_client, email)
    headers = login(api_client, email)
    api_client.get("/users/me", headers=headers)
    api_client.post("/auth/token", data={"username": email, "password": "wrong-password-123"})
    api_client.post("/auth/register", json={"email": email, "password": PASSWORD})  # 409

    password_hash = session.scalar(select(User.password_hash).where(User.email == email))
    token = headers["Authorization"].removeprefix("Bearer ")
    output = "\n".join(logs.lines)
    assert logs.lines
    for secret in (PASSWORD, "wrong-password-123", password_hash, token):
        assert secret
        assert secret not in output


def test_the_engine_hides_sql_parameters() -> None:
    # Integrity errors would otherwise quote the row's values (a password hash) in messages.
    assert get_engine().hide_parameters is True
