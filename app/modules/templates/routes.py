# File: app/modules/templates/routes.py
"""
===============================================================================
TEMPLATE MODULE ROUTES (API TRANSPORT LAYER)
===============================================================================

This module defines the HTTP interface for the Template domain.

It exposes RESTful endpoints that allow external clients to perform
operations such as:

    • creating templates
    • retrieving a template
    • updating a template
    • deleting a template
    • listing templates with pagination

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This file belongs strictly to the **API Transport Layer**.

It is responsible only for:

    • defining HTTP routes
    • validating incoming request schemas
    • invoking service layer methods
    • returning standardized API responses

This module MUST NOT:

    ✘ contain business logic
    ✘ perform database operations
    ✘ directly interact with repositories
    ✘ manage database transactions
    ✘ manipulate infrastructure adapters

All domain logic must live inside:

    service.py

-------------------------------------------------------------------------------
OPENAPI DOCUMENTATION STRATEGY
-------------------------------------------------------------------------------

All OpenAPI documentation is centralized in:

    openapi.py

This includes:

    • endpoint descriptions
    • request examples
    • response schemas
    • error examples
    • OpenAPI metadata

Routes only import predefined OpenAPI blocks:

    from .openapi import CREATE_TEMPLATE_OPENAPI

and attach them directly:

    @router.post("", **CREATE_TEMPLATE_OPENAPI)

This ensures:

    • routes remain extremely clean
    • documentation is centralized
    • OpenAPI specs remain maintainable
    • Swagger examples remain consistent

-------------------------------------------------------------------------------
DEPENDENCY FLOW
-------------------------------------------------------------------------------

The complete execution flow for each request:

    HTTP Request
        ↓
    FastAPI Router
        ↓
    Dependency Injection
        ↓
    TemplateService (Service Layer)
        ↓
    UnitOfWork (Transaction Boundary)
        ↓
    TemplateRepository
        ↓
    Database Adapter
        ↓
    SQL Database

-------------------------------------------------------------------------------
RATE LIMITING
-------------------------------------------------------------------------------

Endpoints may optionally use the rate limiting decorator:

    @rate_limit(limit=20, window_seconds=60)

This decorator integrates with the application's centralized
rate limiting middleware and Redis backend.

Rate limiting is applied selectively depending on endpoint behavior:

    • write operations → stricter limits
    • read operations → more relaxed limits

-------------------------------------------------------------------------------
RESPONSE CONTRACT
-------------------------------------------------------------------------------

All responses must be generated using:

    APIResponse.success()
    APIResponse.error()

defined in:

    app/common/response.py

This ensures every API response follows the unified contract:

{
    "success": true,
    "status": "success",
    "code": 200,
    "message": "...",
    "data": {...},
    "meta": {...}
}

This guarantees:

    • consistent API responses
    • request tracing via request_id
    • unified error handling
    • backward compatible schema evolution

-------------------------------------------------------------------------------
TRANSACTION MANAGEMENT
-------------------------------------------------------------------------------

Routes NEVER manage database transactions.

Transactions are handled exclusively inside the service layer
using the UnitOfWork abstraction:

    async with UnitOfWork:

This ensures:

    • deterministic transaction boundaries
    • consistent commit/rollback behavior
    • repository independence

-------------------------------------------------------------------------------
DESIGN PRINCIPLES
-------------------------------------------------------------------------------

The route layer intentionally follows these design rules:

    • extremely thin controllers
    • strict separation of concerns
    • dependency injection for services
    • centralized OpenAPI documentation
    • unified response envelope
    • framework isolation from business logic

This approach improves:

    • long-term maintainability
    • developer onboarding
    • testability
    • API consistency across modules
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.common.response import APIResponse, Pagination
from app.core.rate_limit import rate_limit

from .schemas import (
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    TemplateListQuery,
)

from .dependencies import get_template_service
from .service import TemplateService

from .openapi import (
    CREATE_TEMPLATE_OPENAPI,
    GET_TEMPLATE_OPENAPI,
    UPDATE_TEMPLATE_OPENAPI,
    DELETE_TEMPLATE_OPENAPI,
    LIST_TEMPLATES_OPENAPI,
)


# =============================================================================
# ROUTER
# =============================================================================

router = APIRouter(
    prefix="/templates",
    tags=["Templates"],
)


# =============================================================================
# CREATE TEMPLATE
# =============================================================================

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    **CREATE_TEMPLATE_OPENAPI,
)
@rate_limit(limit=20, window_seconds=60)
async def create_template(
    payload: TemplateCreate,
    service: TemplateService = Depends(get_template_service),
):

    template = await service.create_template(payload)

    return APIResponse.success(
        message="Template created successfully",
        data=TemplateResponse.model_validate(template),
        code=status.HTTP_201_CREATED,
    )


# =============================================================================
# GET TEMPLATE
# =============================================================================

@router.get(
    "/{template_id}",
    **GET_TEMPLATE_OPENAPI,
)
async def get_template(
    template_id: int,
    service: TemplateService = Depends(get_template_service),
):

    template = await service.get_template(template_id)

    return APIResponse.success(
        data=TemplateResponse.model_validate(template),
    )


# =============================================================================
# UPDATE TEMPLATE
# =============================================================================

@router.put(
    "/{template_id}",
    **UPDATE_TEMPLATE_OPENAPI,
)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    service: TemplateService = Depends(get_template_service),
):

    template = await service.update_template(
        template_id=template_id,
        payload=payload,
    )

    return APIResponse.success(
        message="Template updated successfully",
        data=TemplateResponse.model_validate(template),
    )


# =============================================================================
# DELETE TEMPLATE
# =============================================================================

@router.delete(
    "/{template_id}",
    **DELETE_TEMPLATE_OPENAPI,
)
async def delete_template(
    template_id: int,
    service: TemplateService = Depends(get_template_service),
):

    await service.delete_template(template_id)

    return APIResponse.success(
        message="Template deleted successfully",
    )


# =============================================================================
# LIST TEMPLATES
# =============================================================================

@router.get(
    "",
    **LIST_TEMPLATES_OPENAPI,
)
async def list_templates(
    query: TemplateListQuery = Depends(),
    service: TemplateService = Depends(get_template_service),
):

    templates, total, pagination = await service.list_templates(
        limit=query.limit,
        offset=query.offset,
        status=query.status,
    )

    items = [
        TemplateResponse.model_validate(template)
        for template in templates
    ]

    return APIResponse.success(
        data=items,
        pagination=Pagination(**pagination),
    )


__all__ = ["router"]