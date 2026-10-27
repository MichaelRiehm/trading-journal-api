"""Structured logging: one JSON object per line on stdout (ADR 0014).

What is logged is decided here, by allowlist. Request headers, bodies, query strings and
database parameters are never logged, so passwords, hashes and tokens can't leak.
"""

import json
import logging
import logging.config
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    # Separate from Settings, so configuring logging needs no JWT key or database URL.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@dataclass(slots=True)
class RequestContext:
    """Per-request values that every log line and error body can see.

    Mutable on purpose: a sync dependency runs in a worker thread with a *copy* of the
    context, so setting a ContextVar there would not be seen by the middleware. Mutating
    the object the ContextVar points to is.
    """

    request_id: str
    user_id: str | None = None


request_context: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)

# The only `extra=` keys that reach the output. Anything else is dropped.
EXTRA_FIELDS = ("method", "path", "status", "duration_ms")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (ctx := request_context.get()) is not None:
            entry["request_id"] = ctx.request_id
            if ctx.user_id is not None:
                entry["user_id"] = ctx.user_id
        for key in EXTRA_FIELDS:
            if (value := record.__dict__.get(key)) is not None:
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Send every logger, uvicorn's included, through one JSON handler. Idempotent."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"level": level, "handlers": ["stdout"]},
            "loggers": {
                # Uvicorn installs its own text handlers; drop them and propagate to root.
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                # Our middleware writes the access line (with the request id) instead.
                "uvicorn.access": {"handlers": [], "propagate": False, "level": "WARNING"},
            },
        }
    )
