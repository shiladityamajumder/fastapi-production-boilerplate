# File: app/modules/templates/schemas.py
"""
===============================================================================
TEMPLATE MODULE SCHEMAS (DTO LAYER)
===============================================================================

Defines all data transfer objects used by the Template module.

Schemas represent the contract between:

    • HTTP layer (routes)
    • service layer
    • external API consumers

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Schemas are responsible for:

    • request validation
    • response serialization
    • API documentation
    • schema version stability

Schemas MUST NOT:

    ✘ contain business logic
    ✘ perform database operations
    ✘ access repositories
    ✘ depend on infrastructure adapters

-------------------------------------------------------------------------------
SCHEMA CATEGORIES
-------------------------------------------------------------------------------

1. Request Schemas
        Incoming client payloads

2. Response Schemas
        Outgoing API responses

3. Query Schemas
        Query parameters for list endpoints

4. Internal DTOs
        Service-layer objects

-------------------------------------------------------------------------------
VERSIONING NOTE
-------------------------------------------------------------------------------

Schemas define the **public API contract**.

Breaking changes must be versioned through API versioning.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .constants import (
    TemplateStatus,
    NAME_MIN_LENGTH,
    NAME_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    DEFAULT_LIMIT,
    MAX_LIMIT,
)


# =============================================================================
# BASE SCHEMA
# =============================================================================


class TemplateBase(BaseModel):
    """
    Shared fields for Template schemas.

    This base class ensures consistent typing across:
        - create
        - update
        - response models
    """

    name: str = Field(
        ...,
        min_length=NAME_MIN_LENGTH,
        max_length=NAME_MAX_LENGTH,
        description="Human-readable template name",
        examples=["Welcome Email Template"],
    )

    description: Optional[str] = Field(
        None,
        max_length=DESCRIPTION_MAX_LENGTH,
        description="Optional template description",
        examples=["Template used for onboarding emails"],
    )


# =============================================================================
# CREATE SCHEMA
# =============================================================================


class TemplateCreate(TemplateBase):
    """
    Request schema for creating a template.

    Example payload:

        {
            "name": "Welcome Email",
            "description": "Template for onboarding emails"
        }
    """

    status: TemplateStatus = Field(
        default=TemplateStatus.ACTIVE,
        description="Initial template status",
    )


# =============================================================================
# UPDATE SCHEMA
# =============================================================================


class TemplateUpdate(BaseModel):
    """
    Request schema for updating a template.

    Fields are optional to allow partial updates.
    """

    name: Optional[str] = Field(
        None,
        min_length=NAME_MIN_LENGTH,
        max_length=NAME_MAX_LENGTH,
        description="Updated template name",
    )

    description: Optional[str] = Field(
        None,
        max_length=DESCRIPTION_MAX_LENGTH,
        description="Updated description",
    )

    status: Optional[TemplateStatus] = Field(
        None,
        description="Updated template status",
    )


# =============================================================================
# RESPONSE SCHEMA
# =============================================================================


class TemplateResponse(TemplateBase):
    """
    Response schema returned to clients.

    Represents a persisted Template entity.
    """

    id: int = Field(
        ...,
        description="Unique template identifier",
        examples=[101],
    )

    status: TemplateStatus = Field(
        ...,
        description="Current template status",
    )

    created_at: datetime = Field(
        ...,
        description="Creation timestamp",
    )

    updated_at: datetime = Field(
        ...,
        description="Last update timestamp",
    )

    class Config:
        from_attributes = True


# =============================================================================
# LIST QUERY PARAMETERS
# =============================================================================


class TemplateListQuery(BaseModel):
    """
    Query parameters for listing templates.

    Example request:

        GET /templates?limit=20&offset=0
    """

    limit: int = Field(
        DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of records to return",
    )

    offset: int = Field(
        0,
        ge=0,
        description="Pagination offset",
    )

    status: Optional[TemplateStatus] = Field(
        None,
        description="Optional filter by template status",
    )


# =============================================================================
# INTERNAL SERVICE DTO
# =============================================================================


class TemplateDTO(BaseModel):
    """
    Internal data transfer object used inside service layer.

    This DTO isolates service logic from ORM model objects.
    """

    id: int
    name: str
    description: Optional[str]
    status: TemplateStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "TemplateCreate",
    "TemplateUpdate",
    "TemplateResponse",
    "TemplateListQuery",
    "TemplateDTO",
]
