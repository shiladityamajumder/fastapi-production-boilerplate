"""Smoke tests for app creation, configuration, and health routes."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import AppSettings, Environment
from app.db.registry import DatabaseRegistry, HealthStatus
from app.main import create_app, run
from app.modules.auth.dependencies import get_auth_service


def test_app_uses_supplied_configuration(
    app: FastAPI,
    app_settings: AppSettings,
) -> None:
    """App metadata follows the supplied settings."""
    assert app.title == app_settings.PROJECT_NAME
    assert app.version == app_settings.APP_VERSION
    assert app.state.settings is app_settings
    assert app.state.ready is False


def test_app_registers_api_prefix_for_routes(
    app_settings: AppSettings,
    monkeypatch,
) -> None:
    """Application applies the configured prefix to registered v1 routes."""
    api_router = APIRouter()

    @api_router.get("/smoke")
    async def smoke_route() -> dict[str, str]:
        return {"status": "ok"}

    monkeypatch.setattr("app.main.api_v1_router", api_router)
    app = create_app(app_settings)

    assert f"{app_settings.API_V1_STR}/smoke" in {
        route.path for route in app.routes
    }


def test_settings_reject_invalid_server_port() -> None:
    """Configuration validation rejects values outside the port range."""
    with pytest.raises(ValidationError):
        AppSettings(PORT=0)


def test_console_entry_point_uses_server_configuration(
    app_settings: AppSettings,
    monkeypatch,
) -> None:
    """The project script target starts Uvicorn with validated settings."""
    uvicorn_run = Mock()
    monkeypatch.setattr("app.main.get_settings", lambda: app_settings)
    monkeypatch.setattr("uvicorn.run", uvicorn_run)

    run()

    uvicorn_run.assert_called_once_with(
        "app.main:app",
        host=app_settings.HOST,
        port=app_settings.PORT,
        reload=app_settings.DEBUG,
    )


def test_readiness_returns_unavailable_before_startup(
    app: FastAPI,
) -> None:
    """Readiness is unavailable until the application lifespan starts."""
    test_client = TestClient(app)
    response = test_client.get("/health/ready")
    test_client.close()

    assert response.status_code == 503
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "SERVICE_NOT_READY"


def test_health_endpoints_with_databases_disabled(
    client: TestClient,
) -> None:
    """Health routes retain their response envelope with no configured DBs."""
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    deep = client.get("/health/deep")

    assert live.status_code == 200
    assert live.json()["success"] is True
    assert live.json()["data"] == {"status": "alive"}

    assert ready.status_code == 200
    assert ready.json()["success"] is True
    assert ready.json()["data"] == {"ready": True, "checks": {}}

    assert deep.status_code == 200
    assert deep.json()["success"] is True
    assert deep.json()["data"]["healthy"] is True
    assert deep.json()["data"]["checks"] == {}


def test_lifespan_starts_and_stops_empty_registry(
    app: FastAPI,
    monkeypatch,
) -> None:
    """Lifespan validates and closes the empty registry when DBs are off."""
    ping_all = AsyncMock()
    close = AsyncMock()
    original_from_settings = DatabaseRegistry.from_settings

    def make_registry(
        _cls: type[DatabaseRegistry],
        settings: AppSettings,
    ) -> DatabaseRegistry:
        registry = original_from_settings(settings)
        registry.ping_all = ping_all
        registry.close = close
        return registry

    monkeypatch.setattr(
        DatabaseRegistry,
        "from_settings",
        classmethod(make_registry),
    )

    with TestClient(app):
        registry = app.state.db
        assert registry.adapter_names == ()
        assert app.state.ready is True

    assert ping_all.await_count == 1
    assert close.await_count == 1
    assert app.state.ready is False


def test_readiness_reports_postgres_connectivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings(
        ENVIRONMENT=Environment.TESTING,
        ENABLE_POSTGRES=True,
        POSTGRES_URL="postgresql+asyncpg://user:password@localhost/test_db",
        LOG_TO_FILE=False,
    )
    check_all = AsyncMock(
        return_value={"postgres": HealthStatus(healthy=False, duration_ms=1)}
    )
    original_from_settings = DatabaseRegistry.from_settings

    def make_registry(
        _cls: type[DatabaseRegistry], settings: AppSettings
    ) -> DatabaseRegistry:
        registry = original_from_settings(settings)
        registry.ping_all = AsyncMock()
        registry.check_all = check_all
        registry.close = AsyncMock()
        return registry

    monkeypatch.setattr(
        DatabaseRegistry,
        "from_settings",
        classmethod(make_registry),
    )
    application = create_app(settings)
    with TestClient(application) as test_client:
        response = test_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["postgres"][
        "healthy"
    ] is False
    check_all.assert_awaited_once()


def test_cors_preflight_is_limited_to_configured_origins() -> None:
    settings = AppSettings(
        ENVIRONMENT=Environment.TESTING,
        CORS_ALLOWED_ORIGINS=["https://client.example"],
        CORS_ALLOW_CREDENTIALS=True,
        LOG_TO_FILE=False,
    )
    application = create_app(settings)

    with TestClient(application) as test_client:
        allowed = test_client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        denied = test_client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.headers["access-control-allow-origin"] == "https://client.example"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in denied.headers


def test_database_errors_use_safe_standard_responses(
    client: TestClient,
    app: FastAPI,
) -> None:
    @app.get("/_test/database-conflict", include_in_schema=False)
    async def database_conflict() -> None:
        raise IntegrityError("INSERT", {}, RuntimeError("duplicate secret"))

    @app.get("/_test/database-unavailable", include_in_schema=False)
    async def database_unavailable() -> None:
        raise SQLAlchemyError("database secret")

    conflict = client.get("/_test/database-conflict")
    unavailable = client.get("/_test/database-unavailable")

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "RESOURCE_CONFLICT"
    assert "duplicate secret" not in conflict.text
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "DATABASE_ERROR"
    assert "database secret" not in unavailable.text


def test_protected_profile_route_requires_bearer_authentication(
    client: TestClient,
    app: FastAPI,
) -> None:
    app.dependency_overrides[get_auth_service] = lambda: None
    try:
        response = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_auth_service, None)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
