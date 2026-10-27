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
