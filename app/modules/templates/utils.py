# File: app/modules/templates/utils.py
"""
===============================================================================
TEMPLATE MODULE UTILITIES
===============================================================================

Provides helper utilities used by the Template module.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the **utility layer**.

Responsibilities:

    • provide reusable helper functions
    • perform simple transformations
    • assist DTO conversions
    • assist pagination calculations

This module MUST NOT:

    ✘ perform database queries
    ✘ access repositories
    ✘ implement business logic
    ✘ depend on FastAPI request objects

Utilities should remain:

    • stateless
    • deterministic
    • side-effect free
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from .schemas import TemplateDTO
from .models import Template


# =============================================================================
# DTO CONVERSION HELPERS
# =============================================================================


def to_template_dto(template: Template) -> TemplateDTO:
    """
    Convert ORM Template model into TemplateDTO.

    This prevents ORM objects from leaking into
    service or API layers.
    """

    return TemplateDTO.model_validate(template)


def to_template_dto_list(
    templates: Iterable[Template],
) -> List[TemplateDTO]:
    """
    Convert a sequence of Template ORM models into DTO list.
    """

    return [TemplateDTO.model_validate(t) for t in templates]


# =============================================================================
# PAGINATION UTILITIES
# =============================================================================


def calculate_has_next(
    *,
    total: int,
    offset: int,
    limit: int,
) -> bool:
    """
    Determine if another page exists.

    Used to compute pagination metadata.

    Example:

        total=100
        offset=0
        limit=20

        → has_next = True
    """

    return (offset + limit) < total


def build_pagination_meta(
    *,
    total: int,
    limit: int,
    offset: int,
) -> dict:
    """
    Build pagination metadata structure.

    Compatible with APIResponse pagination contract.
    """

    return {
        "total_count": total,
        "limit": limit,
        "offset": offset,
        "has_next": calculate_has_next(
            total=total,
            offset=offset,
            limit=limit,
        ),
    }


# =============================================================================
# VALIDATION HELPERS
# =============================================================================


def normalize_template_name(name: str) -> str:
    """
    Normalize template name before persistence.

    Ensures consistent storage format.
    """

    return name.strip()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "to_template_dto",
    "to_template_dto_list",
    "calculate_has_next",
    "build_pagination_meta",
    "normalize_template_name",
]
