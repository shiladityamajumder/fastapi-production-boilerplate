"""Smoke tests for app creation, configuration, and health routes."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import AppSettings
from app.db.registry import DatabaseRegistry
from app.main import create_app, run


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
