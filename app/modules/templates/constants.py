# File: app/modules/templates/constants.py
"""
===============================================================================
TEMPLATE MODULE CONSTANTS
===============================================================================

This module defines all constants used within the Template module.

Keeping constants centralized improves:

    • readability
    • maintainability
    • consistency across layers
    • discoverability for developers

Constants defined here may be used by:

    - models
    - schemas
    - repositories
    - services
    - routes
    - OpenAPI documentation

-------------------------------------------------------------------------------
IMPORTANT RULE
-------------------------------------------------------------------------------

Constants MUST NOT contain runtime state or side effects.

They should only represent immutable configuration values or domain rules.

-------------------------------------------------------------------------------
CONSTANT CATEGORIES
-------------------------------------------------------------------------------

1. Domain Constants
2. Pagination Defaults
3. Validation Constraints
4. Database Metadata
5. Cache Keys (future extension)
"""

from __future__ import annotations

from enum import Enum


# =============================================================================
# DOMAIN ENUMS
# =============================================================================


class TemplateStatus(str, Enum):
    """
    Status values representing template lifecycle state.

    Using Enum provides:

        • validation safety
        • type hints
        • IDE autocomplete
        • OpenAPI schema generation
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


# =============================================================================
# DATABASE METADATA
# =============================================================================


class TemplateTable:
    """
    Database metadata constants.

    Separating these avoids magic strings across the repository layer.
    """

    NAME = "templates"

    COLUMN_ID = "id"
    COLUMN_NAME = "name"
    COLUMN_DESCRIPTION = "description"
    COLUMN_STATUS = "status"
    COLUMN_CREATED_AT = "created_at"
    COLUMN_UPDATED_AT = "updated_at"


# =============================================================================
# PAGINATION DEFAULTS
# =============================================================================

DEFAULT_LIMIT: int = 20
"""
Default number of records returned in list endpoints.
"""

MAX_LIMIT: int = 100
"""
Maximum allowed page size to prevent excessive queries.
"""


# =============================================================================
# VALIDATION LIMITS
# =============================================================================

NAME_MIN_LENGTH: int = 3
NAME_MAX_LENGTH: int = 120

DESCRIPTION_MAX_LENGTH: int = 1000


# =============================================================================
# CACHE KEYS (FUTURE EXTENSION)
# =============================================================================


class TemplateCacheKeys:
    """
    Redis cache keys.

    These are not currently used but defined for
    future caching strategies.
    """

    TEMPLATE_BY_ID = "template:{template_id}"
    TEMPLATE_LIST = "template:list"


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "TemplateStatus",
    "TemplateTable",
    "TemplateCacheKeys",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "NAME_MIN_LENGTH",
    "NAME_MAX_LENGTH",
    "DESCRIPTION_MAX_LENGTH",
]
