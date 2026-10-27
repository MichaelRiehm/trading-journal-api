"""Unit tests for password hashing and tokens. No database needed."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from pydantic import SecretStr, ValidationError

from trading_journal import security
from trading_journal.config import Settings
from trading_journal.domain.errors import AuthenticationError

# 64 bytes, so the HS512 case below fails on the algorithm, not on PyJWT's key-length warning.
KEY = "unit-test-signing-key-0123456789abcdefghijklmnopqrstuvwxyz012345"


def make_settings(key: str = KEY, **overrides: Any) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused@127.0.0.1/unused",
        jwt_secret_key=SecretStr(key),
        **overrides,
    )


SETTINGS = make_settings()


def valid_claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(uuid.uuid7()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": security.TOKEN_ISSUER,
        "aud": security.TOKEN_AUDIENCE,
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def sign(claims: dict[str, Any], key: str = KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


def test_password_hash_verifies_and_is_argon2id() -> None:
    hashed = security.hash_password("a long enough password")

    assert hashed.startswith("$argon2id$")
    assert security.verify_password("a long enough password", hashed) == (True, None)
    assert security.verify_password("the wrong password", hashed)[0] is False


def test_same_password_hashes_differently() -> None:
    # Each hash gets its own random salt.
    assert security.hash_password("same password") != security.hash_password("same password")


def test_token_round_trip() -> None:
    user_id = uuid.uuid7()

    token = security.create_access_token(user_id, SETTINGS)

    assert security.decode_access_token(token, SETTINGS) == user_id


def test_token_expires_after_configured_minutes() -> None:
    issued = datetime.now(UTC) - timedelta(minutes=61)
    token = security.create_access_token(uuid.uuid7(), SETTINGS, now=issued)

    with pytest.raises(AuthenticationError):
        security.decode_access_token(token, SETTINGS)


def test_tampered_signature_is_rejected() -> None:
    token = security.create_access_token(uuid.uuid7(), SETTINGS)
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}{'AA' if signature[-2:] != 'AA' else 'BB'}"

    with pytest.raises(AuthenticationError):
        security.decode_access_token(tampered, SETTINGS)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(
            sign(valid_claims(), key="a-different-key-0123456789-abcdefghij"), id="wrong-key"
        ),
        pytest.param(jwt.encode(valid_claims(), key="", algorithm="none"), id="alg-none"),
        pytest.param(sign(valid_claims(), algorithm="HS512"), id="other-algorithm"),
        pytest.param(sign(valid_claims(aud="someone-else")), id="wrong-audience"),
        pytest.param(sign(valid_claims(iss="someone-else")), id="wrong-issuer"),
        pytest.param(sign(valid_claims(sub=None)), id="missing-sub"),
        pytest.param(sign(valid_claims(exp=None)), id="missing-exp"),
        pytest.param(sign(valid_claims(sub="not-a-uuid")), id="sub-not-uuid"),
        pytest.param("not.a.jwt", id="garbage"),
        pytest.param("", id="empty"),
    ],
)
def test_bad_tokens_are_rejected(token: str) -> None:
    with pytest.raises(AuthenticationError):
        security.decode_access_token(token, SETTINGS)


def test_short_signing_key_is_refused_without_echoing_it() -> None:
    with pytest.raises(ValidationError, match="jwt_secret_key") as excinfo:
        make_settings(key="too-short")

    assert "too-short" not in str(excinfo.value)
