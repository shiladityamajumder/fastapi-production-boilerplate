# File: app/modules/templates/service.py
"""
===============================================================================
TEMPLATE SERVICE
===============================================================================

Implements business logic for Template operations.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the **service layer**.

Responsibilities:

    • enforce business rules
    • orchestrate repository operations
    • manage transaction boundaries (UnitOfWork)
    • transform ORM models into DTOs
    • normalize error handling via execution wrapper

This module MUST NOT:

    ✘ perform raw database queries
    ✘ depend on FastAPI request objects
    ✘ construct HTTP responses
    ✘ access infrastructure adapters directly

-------------------------------------------------------------------------------
TRANSACTION MANAGEMENT
-------------------------------------------------------------------------------

All write operations must execute inside:

    async with UnitOfWork:

Repositories remain transaction-agnostic.

-------------------------------------------------------------------------------
ERROR HANDLING
-------------------------------------------------------------------------------

Unexpected errors are normalized through:

    execute_service_operation()

Domain failures raise APIException subclasses.
"""

from __future__ import annotations

from typing import List, Tuple

from app.common.exceptions import NotFoundError
from app.core.execution import execute_service_operation
from app.db.unit_of_work import UnitOfWork

from .repository import TemplateRepository
from .schemas import (
    TemplateCreate,
    TemplateUpdate,
    TemplateDTO,
)
from .constants import TemplateStatus
from .utils import (
    to_template_dto,
    to_template_dto_list,
    normalize_template_name,
    build_pagination_meta,
)


# =============================================================================
# TEMPLATE SERVICE
# =============================================================================


class TemplateService:
    """
    Service responsible for Template domain operations.

    The service layer coordinates repository calls and enforces
    business rules while keeping transaction management isolated
    through UnitOfWork.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        """
        Initialize service with UnitOfWork.

        Args:
            uow:
                Transaction boundary abstraction.
        """
        self.uow = uow

    # -------------------------------------------------------------------------
    # CREATE TEMPLATE
    # -------------------------------------------------------------------------

    async def create_template(self, payload: TemplateCreate) -> TemplateDTO:
        """
        Create a new Template.

        Args:
            payload:
                TemplateCreate schema.

        Returns:
            TemplateDTO
        """

        async def operation() -> TemplateDTO:

            async with self.uow:

                repo = TemplateRepository(self.uow.session)

                template = await repo.create(
                    name=normalize_template_name(payload.name),
                    description=payload.description,
                    status=payload.status,
                )

                return to_template_dto(template)

        return await execute_service_operation(
            operation="template creation",
            func=operation,
            error_message="Failed to create template",
        )

    # -------------------------------------------------------------------------
    # GET TEMPLATE
    # -------------------------------------------------------------------------

    async def get_template(self, template_id: int) -> TemplateDTO:
        """
        Retrieve template by ID.

        Raises:
            NotFoundError if template does not exist.
        """

        async def operation() -> TemplateDTO:

            repo = TemplateRepository(self.uow.session)

            template = await repo.get_by_id(template_id)

            if not template:
                raise NotFoundError("Template not found")

            return to_template_dto(template)

        return await execute_service_operation(
            operation="template retrieval",
            func=operation,
        )

    # -------------------------------------------------------------------------
    # UPDATE TEMPLATE
    # -------------------------------------------------------------------------

    async def update_template(
        self,
        template_id: int,
        payload: TemplateUpdate,
    ) -> TemplateDTO:
        """
        Update an existing Template.
        """

        async def operation() -> TemplateDTO:

            async with self.uow:

                repo = TemplateRepository(self.uow.session)

                template = await repo.get_by_id(template_id)

                if not template:
                    raise NotFoundError("Template not found")

                updated = await repo.update(
                    template,
                    name=normalize_template_name(payload.name)
                    if payload.name
                    else None,
                    description=payload.description,
                    status=payload.status,
                )

                return to_template_dto(updated)

        return await execute_service_operation(
            operation="template update",
            func=operation,
            error_message="Failed to update template",
        )

    # -------------------------------------------------------------------------
    # DELETE TEMPLATE
    # -------------------------------------------------------------------------

    async def delete_template(self, template_id: int) -> None:
        """
        Delete a template by ID.
        """

        async def operation() -> None:

            async with self.uow:

                repo = TemplateRepository(self.uow.session)

                template = await repo.get_by_id(template_id)

                if not template:
                    raise NotFoundError("Template not found")

                await repo.delete(template)

        await execute_service_operation(
            operation="template deletion",
            func=operation,
            error_message="Failed to delete template",
        )

    # -------------------------------------------------------------------------
    # LIST TEMPLATES
    # -------------------------------------------------------------------------

    async def list_templates(
        self,
        *,
        limit: int,
        offset: int,
        status: TemplateStatus | None,
    ) -> Tuple[List[TemplateDTO], int, dict]:
        """
        Retrieve paginated list of templates.

        Returns:
            tuple containing:

                - List[TemplateDTO]
                - total_count
                - pagination metadata
        """

        async def operation():

            repo = TemplateRepository(self.uow.session)

            templates = await repo.list_templates(
                limit=limit,
                offset=offset,
                status=status,
            )

            total = await repo.count_templates(status=status)

            items = to_template_dto_list(templates)

            pagination = build_pagination_meta(
                total=total,
                limit=limit,
                offset=offset,
            )

            return items, total, pagination

        return await execute_service_operation(
            operation="template listing",
            func=operation,
        )
