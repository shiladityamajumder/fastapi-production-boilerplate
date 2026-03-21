"""
===============================================================================
API V1 ROUTER REGISTRY
===============================================================================

Central router registry for API version v1.

This module aggregates routers from all feature modules and exposes
them under the `/api/v1` namespace.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module acts as the **version boundary** for the API.

Responsibilities:

    • collect routers from feature modules
    • apply version prefixing (/api/v1)
    • provide a single router exported to main.py
    • keep routing modular and scalable

This module MUST NOT:

    ✘ contain business logic
    ✘ access databases
    ✘ import repositories or services
    ✘ define HTTP endpoints

Endpoints must only exist inside module-level routers.

-------------------------------------------------------------------------------
ROUTING FLOW
-------------------------------------------------------------------------------

Incoming request:

    HTTP Request
        ↓
    FastAPI App (main.py)
        ↓
    api_router (this file)
        ↓
    Module Router
        ↓
    Endpoint Handler
        ↓
    Service Layer
        ↓
    Repository
        ↓
    Database

-------------------------------------------------------------------------------
URL STRUCTURE
-------------------------------------------------------------------------------

Example routes exposed by this router:

    /api/v1/templates
    /api/v1/templates/{id}

Future modules can be mounted here:

    /api/v1/products
    /api/v1/orders
    /api/v1/users

-------------------------------------------------------------------------------
MODULE REGISTRATION RULE
-------------------------------------------------------------------------------

Each module must expose a router named:

    router

Example:

    modules/templates/routes.py

        router = APIRouter(
            prefix="/templates",
            tags=["Templates"],
        )

This registry imports and attaches that router.

-------------------------------------------------------------------------------
ADDING NEW MODULES
-------------------------------------------------------------------------------

To register a new module:

1 Create module router

    app/modules/products/routes.py

2 Import router here

    from app.modules.products.routes import router as products_router

3 Register it

    router.include_router(products_router)
"""

from fastapi import APIRouter

# =============================================================================
# MODULE ROUTER IMPORTS
# =============================================================================

# Template module
from app.modules.templates.routes import router as templates_router

# Product module
# from app.modules.product.routes import router as product_router


# =============================================================================
# API VERSION ROUTER
# =============================================================================

router = APIRouter(
    prefix="/api/v1",
)


# =============================================================================
# MODULE ROUTER REGISTRATION
# =============================================================================

router.include_router(templates_router)
# router.include_router(product_router)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "router",
]
