"""Application settings, read from environment variables (and `.env` when present)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """What the database tooling needs: Alembic, the engine and the test fixtures.

    Kept separate so the migrate container runs without the JWT signing key.
    """

    # hide_input_in_errors: a rejected value (a short key, a URL with a password) must not
    # be echoed into startup logs.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:password@localhost:5432/journal
    database_url: str
    # Optional; tests default to database_url with "_test" appended to the database name.
    test_database_url: str | None = None


class Settings(DatabaseSettings):
    """Everything the API needs. See docs/decisions/0005-access-tokens.md."""

    # No default: a missing key fails at startup instead of signing with a guessable one.
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()


@lru_cache
def get_settings() -> Settings:
    # Settings are required at runtime, but read lazily so importing the app needs no env.
    return Settings()
