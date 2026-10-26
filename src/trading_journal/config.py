"""Application settings, read from environment variables (and `.env` when present)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:password@localhost:5432/journal
    database_url: str
    # Optional; tests default to database_url with "_test" appended to the database name.
    test_database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    # Settings are required at runtime, but read lazily so importing the app needs no env.
    return Settings()
