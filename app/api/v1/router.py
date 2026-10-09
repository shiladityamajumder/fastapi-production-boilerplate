"""File: app/api/v1/router.py.

Version-one API router registry.

Feature modules define their own path prefixes, tags, request schemas, and
OpenAPI metadata. This module combines those routers under the API prefix
configured in ``app/core/config.py``.

Authentication use cases apply PostgreSQL-backed rate limits so counters are
shared across API worker processes.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.auth.admin_router import router as admin_router
from app.modules.auth.router import router as auth_router


router = APIRouter()
router.include_router(auth_router)
router.include_router(admin_router)


# Keep feature registration explicit. This makes enabled API modules easy to
# discover and avoids dynamic import behavior during application startup.


__all__ = [
    "router",
]
