"""File: app/main.py.

FastAPI application composition root.

This module creates the application, registers global middleware and exception
handlers, attaches routers, and exposes the default ASGI application used by
Uvicorn or another ASGI server.

Business logic and infrastructure implementation must not be placed here.
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.health import router as health_router
from app.api.v1.router import router as api_v1_router
from app.common.response import APIResponse
from app.core.config import (
    AppSettings,
    Environment,
    get_settings,
)
from app.core.lifespan import lifespan
from app.core.logging import setup_logging
from app.core.middleware import register_middleware


def create_app(
    settings: AppSettings | None = None,
) -> FastAPI:
    """Build and configure an isolated FastAPI application instance.

    Args:
        settings: Optional validated settings override. Tests may provide an
            explicit settings instance, while normal runtime execution uses
            the cached environment-driven configuration.

    Returns:
        Fully configured FastAPI application.
    """
    resolved_settings = settings or get_settings()

    # Logging is configured before application startup so initialization
    # failures are emitted through the same structured logging pipeline.
    setup_logging(resolved_settings)

    # Public API documentation is disabled in production by default. Internal
    # teams can expose it through a separate protected environment if needed.
    docs_enabled = resolved_settings.ENVIRONMENT != Environment.PRODUCTION

    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.APP_VERSION,
        debug=resolved_settings.DEBUG,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
        swagger_ui_parameters={
            "persistAuthorization": False,
        },
    )

    # Settings are stored once and reused by dependencies and lifecycle code.
    app.state.settings = resolved_settings

    # The lifespan handler changes this to True only after all required
    # infrastructure dependencies have passed their startup checks.
    app.state.ready = False

    # Middleware must be registered before routes begin handling requests.
    register_middleware(
        app=app,
        settings=resolved_settings,
    )

    register_exception_handlers(app)

    # Health endpoints intentionally remain outside the versioned API prefix.
    app.include_router(health_router)

    app.include_router(
        api_v1_router,
        prefix=resolved_settings.API_V1_STR,
    )

    @app.get(
        "/",
        tags=["System"],
        summary="Service descriptor",
        include_in_schema=docs_enabled,
    )
    async def root():
        """Return non-sensitive service discovery information.

        The endpoint does not expose environment variables, enabled database
        names, connection details, secrets, or infrastructure addresses.
        """
        return APIResponse.success(
            message="Service information retrieved successfully",
            data={
                "service": resolved_settings.PROJECT_NAME,
                "version": resolved_settings.APP_VERSION,
                "apiBase": resolved_settings.API_V1_STR,
                "documentation": ("/docs" if docs_enabled else None),
                "health": {
                    "liveness": "/health/live",
                    "readiness": "/health/ready",
                    "deep": (
                        "/health/deep"
                        if resolved_settings.DEEP_HEALTH_ENABLED
                        else None
                    ),
                },
            },
        )

    return app


def run() -> None:
    """Run the configured FastAPI application with Uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


# Default ASGI application imported by Uvicorn:
#
#     uvicorn app.main:app
#
# Tests should normally call ``create_app(test_settings)`` instead of sharing
# this process-level instance.
app = create_app()


__all__ = [
    "app",
    "create_app",
    "run",
]
