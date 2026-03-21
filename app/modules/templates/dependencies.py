# File: app/modules/templates/dependencies.py
"""
===============================================================================
TEMPLATE MODULE DEPENDENCIES
===============================================================================

Defines dependency providers used by the Template module.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the **API dependency layer**.

Responsibilities:

    • construct service instances
    • resolve infrastructure dependencies
    • keep routes thin and declarative

Dependencies MUST NOT:

    ✘ contain business logic
    ✘ execute database queries
    ✘ construct HTTP responses

-------------------------------------------------------------------------------
DEPENDENCY FLOW
-------------------------------------------------------------------------------

FastAPI Route
    ↓
Dependency Injection
    ↓
TemplateService
    ↓
UnitOfWork
    ↓
Repository
    ↓
Database

-------------------------------------------------------------------------------
WHY THIS EXISTS
-------------------------------------------------------------------------------

Separating dependencies from routes allows:

    • cleaner route definitions
    • easier testing
    • service reuse
    • modular architecture
"""

from __future__ import annotations

from fastapi import Depends

from app.db.unit_of_work import UnitOfWork
from app.api.dependencies.uow import get_uow

from .service import TemplateService


# =============================================================================
# TEMPLATE SERVICE DEPENDENCY
# =============================================================================


def get_template_service(
    uow: UnitOfWork = Depends(get_uow),
) -> TemplateService:
    """
    Provide TemplateService instance.

    This dependency constructs the service with the required
    UnitOfWork instance for transaction management.

    Example usage in routes:

        @router.post("/templates")
        async def create_template(
            payload: TemplateCreate,
            service: TemplateService = Depends(get_template_service),
        ):
            return await service.create_template(payload)
    """

    return TemplateService(uow=uow)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "get_template_service",
]
