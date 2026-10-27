"""One error format for every response: RFC 9457 problem details (ADR 0013).

Domain errors, request validation, Starlette's HTTP errors (unknown route, wrong method)
and unhandled exceptions (see middleware.py) all become `application/problem+json`.
"""

from collections.abc import Callable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from trading_journal.domain.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
)
from trading_journal.logging_config import request_context

PROBLEM_JSON = "application/problem+json"


class Problem(BaseModel):
    """An error response (RFC 9457). `detail` is the human-readable explanation."""

    type: str = "about:blank"  # no meaning beyond the status code (RFC 9457, 4.2.1)
    title: str
    status: int
    detail: str
    instance: str  # the request path
    request_id: str | None = None  # also in the X-Request-ID header and the logs


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationProblem(Problem):
    """A 422 from request validation. The rejected input is never echoed back."""

    errors: list[FieldError]


# The shape of a route's `responses=` (extra status codes documented in OpenAPI).
type Responses = dict[int | str, dict[str, Any]]


def problem(status_code: int, description: str, model: type[Problem] = Problem) -> Responses:
    """Document an error response with the Problem schema: `responses=problem(404, "...")`."""
    return {status_code: {"model": model, "description": description}}


# For routers whose routes all take `CurrentUser`.
UNAUTHORIZED: Responses = problem(401, "Missing, invalid or expired token")


def problem_response(
    status_code: int,
    detail: str,
    *,
    instance: str,
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    ctx = request_context.get()
    fields: dict[str, Any] = {
        "title": HTTPStatus(status_code).phrase,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "request_id": ctx.request_id if ctx else None,
    }
    body = ValidationProblem(**fields, errors=errors) if errors is not None else Problem(**fields)
    return JSONResponse(
        body.model_dump(mode="json"),
        status_code=status_code,
        headers=headers,
        media_type=PROBLEM_JSON,
    )


_STATUS: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
}


def _domain_responder(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
    # RFC 6750: a 401 for a bearer-protected resource must say how to authenticate.
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None

    def respond(request: Request, exc: Exception) -> JSONResponse:
        detail = exc.message if isinstance(exc, DomainError) else HTTPStatus(status_code).phrase
        return problem_response(status_code, detail, instance=request.url.path, headers=headers)

    return respond


def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only where, what and why. Pydantic's `input` and `ctx` would echo the rejected
    # value, which for /auth/register is the password.
    errors = [FieldError(loc=list(e["loc"]), msg=e["msg"], type=e["type"]) for e in exc.errors()]
    return problem_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "The request is invalid; see errors",
        instance=request.url.path,
        errors=errors,
    )


def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Starlette's own errors: an unknown route (404), a wrong method (405, with Allow).
    detail = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    headers = dict(exc.headers) if exc.headers else None
    return problem_response(exc.status_code, detail, instance=request.url.path, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    for error_type, status_code in _STATUS.items():
        app.add_exception_handler(error_type, _domain_responder(status_code))
    # The decorator form accepts handlers typed for their specific exception.
    app.exception_handler(RequestValidationError)(_validation_error)
    app.exception_handler(StarletteHTTPException)(_http_error)


# Documented on every route: FastAPI then skips its own 422 schema (HTTPValidationError).
APP_RESPONSES: Responses = {
    **problem(422, "The request is invalid", ValidationProblem),
    **problem(500, "Unexpected server error"),
}


def install_openapi(app: FastAPI) -> None:
    """Generate the schema as usual, then list Problem bodies under application/problem+json."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title, version=app.version, summary=app.summary, routes=app.routes
            )
            for path in schema.get("paths", {}).values():
                for operation in path.values():
                    for response in operation.get("responses", {}).values():
                        content = response.get("content", {})
                        body = content.get("application/json", {})
                        if body.get("schema", {}).get("$ref", "").endswith("Problem"):
                            content[PROBLEM_JSON] = content.pop("application/json")
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
