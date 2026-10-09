"""OpenAPI contracts for protected, documented application endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_documents_response_envelopes_and_bearer_security(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()
    paths = document["paths"]
    current_user = paths["/api/v1/auth/me"]["get"]
    security_schemes = document["components"]["securitySchemes"]

    assert current_user["security"]
    assert current_user["security"][0]
    bearer_name = next(iter(current_user["security"][0]))
    assert security_schemes[bearer_name]["scheme"] == "bearer"
    response_schema = current_user["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert "$ref" in response_schema
    wrapper_name = response_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    wrapper_schema = document["components"]["schemas"][wrapper_name]
    assert {"success", "message", "data", "error", "meta"} <= set(
        wrapper_schema["properties"]
    )
    assert "401" in current_user["responses"]
    assert "403" in current_user["responses"]

    upload = paths["/api/v1/auth/files/uploads"]["post"]
    assert upload["security"] == current_user["security"]
    assert "requestBody" in upload
    assert "201" in upload["responses"]


def test_openapi_documents_admin_filters_sorting_and_pagination(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/api/v1/admin/users"]["get"]
    parameters = {
        parameter["name"]: parameter for parameter in operation["parameters"]
    }

    assert {
        "limit",
        "offset",
        "search",
        "role",
        "is_active",
        "sort_by",
        "sort_order",
    } <= set(parameters)
    assert parameters["sort_by"]["schema"]["enum"] == [
        "created_at",
        "email",
        "username",
        "role",
    ]
    assert operation["summary"] == "List users"


def test_openapi_documents_postgres_readiness_failure(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/health/ready"]["get"]

    assert operation["summary"] == "Traffic readiness"
    assert "PostgreSQL" in operation["description"]
    assert "503" in operation["responses"]
