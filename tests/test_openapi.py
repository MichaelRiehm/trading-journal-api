"""The OpenAPI document describes the error format (ADR 0013)."""

from typing import Any

from fastapi.testclient import TestClient


def operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method, path, op) for path, ops in schema["paths"].items() for method, op in ops.items()
    ]


def test_error_schemas_replace_fastapis_defaults(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert {"Problem", "ValidationProblem", "FieldError"} <= schemas.keys()
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas


def test_every_error_response_is_a_problem(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for method, path, op in operations(schema):
        for code, response in op["responses"].items():
            if int(code) < 400 or path == "/ready":  # /ready's 503 is its health body
                continue
            content = response["content"]
            assert list(content) == ["application/problem+json"], (method, path, code)
            ref = content["application/problem+json"]["schema"]["$ref"]
            expected = "ValidationProblem" if code == "422" else "Problem"
            assert ref == f"#/components/schemas/{expected}", (method, path, code)


def test_protected_routes_document_401(client: TestClient) -> None:
    public = {"/health", "/ready", "/auth/register", "/auth/token"}
    schema = client.get("/openapi.json").json()
    for method, path, op in operations(schema):
        if path not in public:
            assert "401" in op["responses"], (method, path)
