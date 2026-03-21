# File: app/modules/templates/repository.py
"""
===============================================================================
TEMPLATE REPOSITORY
===============================================================================

Provides persistence operations for Template entities.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the repository layer.

Responsibilities:

    • Execute database queries
    • Persist ORM models
    • Provide query abstractions for the service layer

This module MUST NOT:

    ✘ contain business logic
    ✘ commit transactions
    ✘ rollback transactions
    ✘ depend on FastAPI

Transaction lifecycle is controlled by:

    UnitOfWork

-------------------------------------------------------------------------------
TRANSACTION RULE
-------------------------------------------------------------------------------

Repositories may call:

    session.flush()

Repositories MUST NOT call:

    session.commit()
    session.rollback()

-------------------------------------------------------------------------------
RETURN VALUES
-------------------------------------------------------------------------------

Repositories return ORM models.

Service layer converts them into DTOs or API schemas.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Template
from .constants import TemplateStatus


# =============================================================================
# TEMPLATE REPOSITORY
# =============================================================================


class TemplateRepository:
    """
    Repository responsible for database operations
    related to Template entities.

    Instances of this repository are expected to be used
    within a UnitOfWork transaction boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with an async SQLAlchemy session.

        Args:
            session:
                SQLAlchemy AsyncSession managed by UnitOfWork.
        """
        self.session = session

    # -------------------------------------------------------------------------
    # CREATE
    # -------------------------------------------------------------------------

    async def create(
        self,
        *,
        name: str,
        description: Optional[str],
        status: TemplateStatus,
    ) -> Template:
        """
        Persist a new Template.

        Args:
            name:
                Template name.

            description:
                Optional description.

            status:
                Template lifecycle status.

        Returns:
            Persisted Template ORM instance.
        """

        template = Template(
            name=name,
            description=description,
            status=status.value,
        )

        self.session.add(template)

        # flush ensures ID is generated immediately
        await self.session.flush()

        return template

    # -------------------------------------------------------------------------
    # GET BY ID
    # -------------------------------------------------------------------------

    async def get_by_id(self, template_id: int) -> Optional[Template]:
        """
        Retrieve a Template by its primary key.

        Args:
            template_id:
                Template identifier.

        Returns:
            Template instance or None if not found.
        """

        stmt = select(Template).where(Template.id == template_id)

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # UPDATE
    # -------------------------------------------------------------------------

    async def update(
        self,
        template: Template,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[TemplateStatus] = None,
    ) -> Template:
        """
        Update fields of an existing Template.

        Only provided fields are modified.

        Args:
            template:
                ORM instance to update.

        Returns:
            Updated Template ORM instance.
        """

        if name is not None:
            template.name = name

        if description is not None:
            template.description = description

        if status is not None:
            template.status = status.value

        await self.session.flush()

        return template

    # -------------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------------

    async def delete(self, template: Template) -> None:
        """
        Remove a Template from the database.
        """

        await self.session.delete(template)

    # -------------------------------------------------------------------------
    # LIST (PAGINATED)
    # -------------------------------------------------------------------------

    async def list_templates(
        self,
        *,
        limit: int,
        offset: int,
        status: Optional[TemplateStatus] = None,
    ) -> Sequence[Template]:
        """
        Retrieve paginated templates.

        Args:
            limit:
                Maximum records to return.

            offset:
                Pagination offset.

            status:
                Optional filter by template status.

        Returns:
            Sequence of Template ORM objects.
        """

        stmt = select(Template)

        if status:
            stmt = stmt.where(Template.status == status.value)

        stmt = (
            stmt.order_by(Template.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)

        return result.scalars().all()

    # -------------------------------------------------------------------------
    # COUNT
    # -------------------------------------------------------------------------

    async def count_templates(
        self,
        *,
        status: Optional[TemplateStatus] = None,
    ) -> int:
        """
        Count total templates for pagination.

        Args:
            status:
                Optional filter by template status.

        Returns:
            Total template count.
        """

        stmt = select(func.count(Template.id))

        if status:
            stmt = stmt.where(Template.status == status.value)

        result = await self.session.execute(stmt)

        return result.scalar_one()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "TemplateRepository",
]
