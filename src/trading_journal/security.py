"""Password hashing and access tokens. Pure functions: no FastAPI, no database.

See docs/decisions/0005-access-tokens.md and docs/decisions/0006-password-handling.md.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from trading_journal.config import Settings
from trading_journal.domain.errors import AuthenticationError

TOKEN_ISSUER = "trading-journal-api"  # noqa: S105 (a claim value, not a secret)
TOKEN_AUDIENCE = "trading-journal-api"  # noqa: S105

# Argon2id with pwdlib's recommended parameters.
_hasher = PasswordHash.recommended()

# Verified against when the email is unknown, so a login for a missing user costs the same
# time as one with a wrong password and the response time doesn't reveal which emails exist.
DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalization")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Return (valid, new_hash). new_hash is set when the stored hash uses old parameters."""
    return _hasher.verify_and_update(password, password_hash)


def create_access_token(user_id: uuid.UUID, settings: Settings, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
    }
    return jwt.encode(
        claims, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Return the user id in a valid token, or raise AuthenticationError."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            # Pinning the algorithm list is what blocks `alg: none` and algorithm confusion.
            algorithms=[settings.jwt_algorithm],
            audience=TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise AuthenticationError("Could not validate credentials") from exc
