import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.orm import Session

from api_helpers import PASSWORD, login, register, registered_headers, unique_email
from trading_journal.config import get_settings
from trading_journal.repositories import UserRepository
from trading_journal.security import create_access_token


def test_register_returns_user_without_password(api_client: TestClient) -> None:
    email = unique_email()

    body = register(api_client, email)

    assert body["email"] == email
    assert set(body) == {"id", "email", "created_at"}
    uuid.UUID(body["id"])


def test_password_is_stored_as_argon2_hash(api_client: TestClient, session: Session) -> None:
    email = unique_email()
    register(api_client, email)

    user = UserRepository(session).get_by_email(email)

    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_email_is_normalized_to_lowercase(api_client: TestClient) -> None:
    body = register(api_client, "  Mixed.Case@Example.COM ")

    assert body["email"] == "mixed.case@example.com"


@pytest.mark.parametrize("second", ["same@example.com", "SAME@example.com"])
def test_duplicate_email_is_a_conflict(api_client: TestClient, second: str) -> None:
    register(api_client, "same@example.com")

    response = api_client.post("/auth/register", json={"email": second, "password": PASSWORD})

    assert response.status_code == 409
    assert response.json()["detail"] == "Email is already registered"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"email": "not-an-email", "password": PASSWORD}, id="bad-email"),
        pytest.param({"email": "a@example.com", "password": "short"}, id="short-password"),
        pytest.param({"email": "a@example.com", "password": "x" * 129}, id="long-password"),
        pytest.param({"email": "a@example.com"}, id="missing-password"),
    ],
)
def test_invalid_registration_is_rejected(api_client: TestClient, payload: dict[str, str]) -> None:
    response = api_client.post("/auth/register", json=payload)

    assert response.status_code == 422


def test_token_for_valid_credentials(api_client: TestClient) -> None:
    email = unique_email()
    register(api_client, email)

    response = api_client.post(
        "/auth/token", data={"username": email.upper(), "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert body["access_token"]


@pytest.mark.parametrize("known_email", [True, False], ids=["wrong-password", "unknown-email"])
def test_bad_credentials_are_unauthorized(api_client: TestClient, known_email: bool) -> None:
    email = unique_email()
    if known_email:
        register(api_client, email)

    response = api_client.post(
        "/auth/token", data={"username": email, "password": "not the right password"}
    )

    # Same status and message either way, so the response doesn't reveal which emails exist.
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_returns_current_user(api_client: TestClient) -> None:
    user, headers = registered_headers(api_client)

    response = api_client.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == user


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-token"),
        pytest.param({"Authorization": "Bearer not-a-token"}, id="garbage-token"),
        pytest.param({"Authorization": "Basic dXNlcjpwYXNz"}, id="wrong-scheme"),
    ],
)
def test_me_without_valid_token_is_unauthorized(
    api_client: TestClient, headers: dict[str, str]
) -> None:
    response = api_client.get("/users/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_expired_token_is_unauthorized(api_client: TestClient) -> None:
    user = register(api_client)
    issued = datetime.now(UTC) - timedelta(minutes=get_settings().access_token_expire_minutes + 1)
    token = create_access_token(uuid.UUID(user["id"]), get_settings(), now=issued)

    response = api_client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_of_deleted_user_is_unauthorized(api_client: TestClient, session: Session) -> None:
    user, headers = registered_headers(api_client)
    db_user = UserRepository(session).get(uuid.UUID(user["id"]))
    assert db_user is not None
    session.delete(db_user)
    session.flush()

    response = api_client.get("/users/me", headers=headers)

    assert response.status_code == 401


def test_login_upgrades_hash_made_with_old_parameters(
    api_client: TestClient, session: Session
) -> None:
    email = unique_email()
    weak = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8 * 1024),)).hash(PASSWORD)
    UserRepository(session).add(email=email, password_hash=weak)

    login(api_client, email)

    user = UserRepository(session).get_by_email(email)
    assert user is not None
    assert user.password_hash != weak
    assert user.password_hash.startswith("$argon2id$")


def test_token_is_independent_of_login_casing(api_client: TestClient) -> None:
    email = unique_email()
    register(api_client, email)

    response = api_client.get("/users/me", headers=login(api_client, email.upper()))

    assert response.json()["email"] == email
