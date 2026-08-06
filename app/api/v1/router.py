"""
File: app/api/v1/router.py

Version-one API router registry.

Feature modules define their own path prefixes, tags, request schemas, and
OpenAPI metadata. This module combines those routers under the API prefix
configured in ``app/core/config.py``.

No rate-limiting dependency is registered because application-level rate
limiting has been removed from this service foundation.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.dummy_items.routes import (
    router as dummy_items_router,
)


router = APIRouter()


# Keep feature registration explicit. This makes enabled API modules easy to
# discover and avoids dynamic import behavior during application startup.
router.include_router(
    dummy_items_router,
)


__all__ = [
    "router",
]