# File: app/main.py
"""
===============================================================================
FASTAPI APPLICATION ENTRYPOINT (COMPOSITION ROOT)
===============================================================================

This module is the **Composition Root** of the application.

The Composition Root is the single location where all application
components are assembled and wired together.

It connects infrastructure, middleware, routing, and lifecycle
management into a fully operational FastAPI application.

-------------------------------------------------------------------------------
RESPONSIBILITIES
-------------------------------------------------------------------------------

This module is responsible for:

    • loading application configuration
    • creating the FastAPI instance
    • registering middleware
    • registering global exception handlers
    • attaching routers
    • connecting lifecycle management
    • exposing operational system endpoints

-------------------------------------------------------------------------------
ARCHITECTURAL BOUNDARY
-------------------------------------------------------------------------------

This module MUST NOT contain:

    ✘ business logic
    ✘ database queries
    ✘ repository usage
    ✘ service orchestration
    ✘ domain rules

Those belong to the following layers:

    Service Layer
        app/modules/*/service.py

    Repository Layer
        app/modules/*/repository.py

    Infrastructure Layer
        app/infrastructure/

The composition root only **assembles the system**.

-------------------------------------------------------------------------------
APPLICATION BOOTSTRAP FLOW
-------------------------------------------------------------------------------

create_app()
    ↓
Load configuration
    ↓
Create FastAPI instance
    ↓
Register middleware
    ↓
Register global exception handlers
    ↓
Register operational routers (health, system)
    ↓
Register versioned API routers
    ↓
Expose service root endpoint
    ↓
Return configured FastAPI instance

-------------------------------------------------------------------------------
ROUTING STRUCTURE
-------------------------------------------------------------------------------

Service descriptor:

    /

Operational endpoints:

    /health/live
    /health/ready
    /health/deep

Versioned API endpoints:

    /api/v1/templates
    /api/v1/products
    /api/v1/...

-------------------------------------------------------------------------------
PRODUCTION HARDENING
-------------------------------------------------------------------------------

The application enforces several production safeguards:

    • FastAPI debug mode is disabled
    • Interactive docs disabled in production
    • Centralized exception handling
    • Infrastructure lifecycle managed via lifespan
    • Versioned routing for backward compatibility
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import router as api_router
from app.api.health import router as health_router

from app.common.exceptions import (
    APIException,
    api_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
)

from app.common.response import APIResponse

from app.core.config import Environment, get_settings
from app.core.lifespan import lifespan
from app.core.middleware import register_middleware


# =============================================================================
# APPLICATION FACTORY
# =============================================================================


def create_app() -> FastAPI:
    """
    Application factory.

    Using an application factory provides several advantages:

        • avoids module-level side effects
        • allows isolated application instances for tests
        • supports dynamic configuration injection
        • improves maintainability in large systems

    Returns
    -------
    FastAPI
        Fully configured FastAPI application instance.
    """

    settings = get_settings()

    # Disable documentation in production
    docs_enabled = settings.ENVIRONMENT != Environment.PRODUCTION

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.API_V1_STR,
        debug=False,  # Debug must never be enabled in production
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # Middleware Registration
    # -------------------------------------------------------------------------
    # Middleware ordering is controlled inside register_middleware().
    register_middleware(app)

    # -------------------------------------------------------------------------
    # Global Exception Handlers
    # -------------------------------------------------------------------------

    app.add_exception_handler(APIException, api_exception_handler)

    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )

    app.add_exception_handler(
        Exception,
        unhandled_exception_handler,
    )

    # -------------------------------------------------------------------------
    # Operational Routers
    # -------------------------------------------------------------------------
    # Infrastructure endpoints such as health checks.

    app.include_router(health_router)

    # -------------------------------------------------------------------------
    # Versioned API Routers
    # -------------------------------------------------------------------------
    # All public APIs are versioned.

    app.include_router(api_router)

    # -------------------------------------------------------------------------
    # SERVICE ROOT ENDPOINT
    # -------------------------------------------------------------------------

    @app.get("/", tags=["System"])
    async def root():
        """
        Service root endpoint.

        Provides basic information about the running service and
        useful operational endpoints.
        """

        return APIResponse.success(
            message=settings.PROJECT_NAME,
            data={
                "service": settings.PROJECT_NAME,
                "version": settings.API_V1_STR,
                "environment": settings.ENVIRONMENT.value,
                "api_base": "/api/v1",
                "documentation": (
                    "/docs"
                    if settings.ENVIRONMENT != Environment.PRODUCTION
                    else None
                ),
                "health_endpoints": {
                    "live": "/health/live",
                    "ready": "/health/ready",
                    "deep": "/health/deep",
                },
            },
        )

    return app


# =============================================================================
# APPLICATION INSTANCE
# =============================================================================

"""
ASGI servers such as Uvicorn or Gunicorn import this variable
as the application entrypoint.

Example:

    uvicorn app.main:app
"""

app = create_app()
