"""Map domain errors to HTTP responses, so routers and services stay free of status codes.

The body is FastAPI's default `{"detail": ...}` for now; Stage 6 settles the error format.
"""

from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from trading_journal.domain.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
)

_STATUS: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
}


def _responder(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
    # RFC 6750: a 401 for a bearer-protected resource must say how to authenticate.
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None

    def respond(_request: Request, exc: Exception) -> JSONResponse:
        detail = exc.message if isinstance(exc, DomainError) else "Error"
        return JSONResponse({"detail": detail}, status_code=status_code, headers=headers)

    return respond


def register_error_handlers(app: FastAPI) -> None:
    for error_type, status_code in _STATUS.items():
        app.add_exception_handler(error_type, _responder(status_code))
